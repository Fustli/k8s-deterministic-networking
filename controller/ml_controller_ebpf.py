#!/usr/bin/env python3
"""
ML-Based QoS Controller with eBPF TCP/UDP Monitoring
Monitors kernel-level socket statistics for both TCP and UDP without L7 overhead
"""

import os
import sys
import time
import logging
import statistics
from datetime import datetime
from kubernetes import client, config
from bcc import BPF

# Configuration from environment variables
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus.monitoring:9090")
TARGET_JITTER_MS = float(os.getenv("TARGET_JITTER_MS", "5.0"))
TARGET_LATENCY_MS = float(os.getenv("TARGET_LATENCY_MS", "10.0"))
MIN_BANDWIDTH_MBPS = int(os.getenv("MIN_BANDWIDTH_MBPS", "10"))
MAX_BANDWIDTH_MBPS = int(os.getenv("MAX_BANDWIDTH_MBPS", "1000"))
EWMA_ALPHA = float(os.getenv("EWMA_ALPHA", "0.7"))
CONTROL_INTERVAL_SEC = int(os.getenv("CONTROL_INTERVAL_SEC", "5"))
COOLDOWN_PERIOD_SEC = int(os.getenv("COOLDOWN_PERIOD_SEC", "30"))
AGGRESSIVE_DECREASE_MBPS = int(os.getenv("AGGRESSIVE_DECREASE_MBPS", "100"))
GENTLE_DECREASE_MBPS = int(os.getenv("GENTLE_DECREASE_MBPS", "30"))
INCREASE_STEP_MBPS = int(os.getenv("INCREASE_STEP_MBPS", "10"))

# Target pods to monitor
CRITICAL_PODS = ["robot-factory", "robot-control", "safety-scanner"]
BEST_EFFORT_DEPLOYMENTS = ["telemetry-upload-deployment", "erp-dashboard-deployment", 
                            "background-traffic-generator"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# eBPF program to track TCP RTT and UDP packet timing
bpf_program = """
#include <uapi/linux/ptrace.h>
#include <net/sock.h>
#include <bcc/proto.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/ip.h>

// Structure to store RTT measurements
struct rtt_event {
    u32 pid;
    u32 saddr;
    u32 daddr;
    u16 sport;
    u16 dport;
    u32 rtt_us;
    u8 protocol;  // 6=TCP, 17=UDP
    u64 timestamp;
};

// Structure for UDP packet timing
struct udp_timing {
    u64 last_send_ts;
    u64 last_recv_ts;
    u32 packet_count;
};

BPF_PERF_OUTPUT(rtt_events);
BPF_HASH(tcp_rtt_map, u64, u32);
BPF_HASH(udp_timing_map, u64, struct udp_timing);

// Track TCP RTT from kernel's perspective
int trace_tcp_rcv_established(struct pt_regs *ctx, struct sock *sk) {
    if (sk == NULL)
        return 0;
    
    // Get TCP socket info
    struct tcp_sock *tp = tcp_sk(sk);
    u32 srtt = tp->srtt_us >> 3;  // Smoothed RTT in microseconds
    
    if (srtt == 0)
        return 0;
    
    // Get connection tuple
    u16 family = sk->__sk_common.skc_family;
    if (family != AF_INET)  // Only IPv4 for now
        return 0;
    
    struct rtt_event evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.saddr = sk->__sk_common.skc_rcv_saddr;
    evt.daddr = sk->__sk_common.skc_daddr;
    evt.sport = sk->__sk_common.skc_num;
    evt.dport = bpf_ntohs(sk->__sk_common.skc_dport);
    evt.rtt_us = srtt;
    evt.protocol = 6;  // TCP
    evt.timestamp = bpf_ktime_get_ns();
    
    // Store in map for aggregation
    u64 key = ((u64)evt.daddr << 32) | evt.dport;
    tcp_rtt_map.update(&key, &srtt);
    
    // Send event
    rtt_events.perf_submit(ctx, &evt, sizeof(evt));
    
    return 0;
}

// Track UDP send timing
int trace_udp_sendmsg(struct pt_regs *ctx, struct sock *sk) {
    if (sk == NULL)
        return 0;
    
    u16 family = sk->__sk_common.skc_family;
    if (family != AF_INET)
        return 0;
    
    u64 key = ((u64)sk->__sk_common.skc_daddr << 32) | 
              bpf_ntohs(sk->__sk_common.skc_dport);
    
    struct udp_timing timing = {};
    struct udp_timing *existing = udp_timing_map.lookup(&key);
    
    if (existing) {
        timing = *existing;
    }
    
    timing.last_send_ts = bpf_ktime_get_ns();
    timing.packet_count++;
    udp_timing_map.update(&key, &timing);
    
    return 0;
}

// Track UDP receive timing
int trace_udp_recvmsg(struct pt_regs *ctx, struct sock *sk) {
    if (sk == NULL)
        return 0;
    
    u16 family = sk->__sk_common.skc_family;
    if (family != AF_INET)
        return 0;
    
    u64 ts_now = bpf_ktime_get_ns();
    u64 key = ((u64)sk->__sk_common.skc_rcv_saddr << 32) | 
              sk->__sk_common.skc_num;
    
    struct udp_timing timing = {};
    struct udp_timing *existing = udp_timing_map.lookup(&key);
    
    if (existing) {
        timing = *existing;
        
        // Calculate inter-packet delay (jitter proxy)
        if (timing.last_recv_ts > 0) {
            u64 delay_ns = ts_now - timing.last_recv_ts;
            u32 delay_us = delay_ns / 1000;
            
            // Create RTT event for UDP (using inter-packet delay)
            struct rtt_event evt = {};
            evt.pid = bpf_get_current_pid_tgid() >> 32;
            evt.saddr = sk->__sk_common.skc_rcv_saddr;
            evt.daddr = sk->__sk_common.skc_daddr;
            evt.sport = sk->__sk_common.skc_num;
            evt.dport = bpf_ntohs(sk->__sk_common.skc_dport);
            evt.rtt_us = delay_us;
            evt.protocol = 17;  // UDP
            evt.timestamp = ts_now;
            
            rtt_events.perf_submit(ctx, &evt, sizeof(evt));
        }
    }
    
    timing.last_recv_ts = ts_now;
    udp_timing_map.update(&key, &timing);
    
    return 0;
}
"""

class eBPFMonitor:
    """Monitor TCP/UDP socket statistics using eBPF"""
    
    def __init__(self):
        self.tcp_rtts = []
        self.udp_delays = []
        self.bpf = None
        
    def start(self):
        """Initialize and attach eBPF program"""
        try:
            logger.info("Loading eBPF program...")
            self.bpf = BPF(text=bpf_program)
            
            # Attach to TCP receive path
            self.bpf.attach_kprobe(event="tcp_rcv_established", 
                                  fn_name="trace_tcp_rcv_established")
            
            # Attach to UDP send/receive
            self.bpf.attach_kprobe(event="udp_sendmsg", 
                                  fn_name="trace_udp_sendmsg")
            self.bpf.attach_kprobe(event="udp_recvmsg", 
                                  fn_name="trace_udp_recvmsg")
            
            logger.info("eBPF probes attached successfully")
            
            # Setup event callback
            self.bpf["rtt_events"].open_perf_buffer(self._handle_event)
            
        except Exception as e:
            logger.error(f"Failed to initialize eBPF: {e}")
            raise
    
    def _handle_event(self, cpu, data, size):
        """Handle RTT events from eBPF"""
        event = self.bpf["rtt_events"].event(data)
        
        rtt_ms = event.rtt_us / 1000.0
        
        if event.protocol == 6:  # TCP
            self.tcp_rtts.append(rtt_ms)
            # Keep only recent measurements
            if len(self.tcp_rtts) > 100:
                self.tcp_rtts.pop(0)
        elif event.protocol == 17:  # UDP
            self.udp_delays.append(rtt_ms)
            if len(self.udp_delays) > 100:
                self.udp_delays.pop(0)
    
    def poll_events(self, timeout_ms=100):
        """Poll for new eBPF events"""
        if self.bpf:
            self.bpf.perf_buffer_poll(timeout=timeout_ms)
    
    def get_metrics(self):
        """Calculate latency and jitter from collected RTT samples"""
        metrics = {
            "tcp_latency_ms": None,
            "tcp_jitter_ms": None,
            "udp_latency_ms": None,
            "udp_jitter_ms": None,
            "sample_count": 0
        }
        
        # TCP metrics
        if len(self.tcp_rtts) >= 5:
            sorted_tcp = sorted(self.tcp_rtts)
            metrics["tcp_latency_ms"] = statistics.quantiles(sorted_tcp, n=20)[18]  # P95
            
            # Calculate IQR jitter
            q1 = statistics.quantiles(sorted_tcp, n=4)[0]  # Q1
            q3 = statistics.quantiles(sorted_tcp, n=4)[2]  # Q3
            metrics["tcp_jitter_ms"] = q3 - q1
            metrics["sample_count"] += len(self.tcp_rtts)
        
        # UDP metrics
        if len(self.udp_delays) >= 5:
            sorted_udp = sorted(self.udp_delays)
            metrics["udp_latency_ms"] = statistics.quantiles(sorted_udp, n=20)[18]  # P95
            
            # Calculate IQR jitter
            q1 = statistics.quantiles(sorted_udp, n=4)[0]
            q3 = statistics.quantiles(sorted_udp, n=4)[2]
            metrics["udp_jitter_ms"] = q3 - q1
            metrics["sample_count"] += len(self.udp_delays)
        
        return metrics
    
    def clear_samples(self):
        """Clear collected samples"""
        self.tcp_rtts.clear()
        self.udp_delays.clear()
    
    def stop(self):
        """Detach eBPF program"""
        if self.bpf:
            logger.info("Detaching eBPF probes...")
            self.bpf.cleanup()


class MLController:
    """ML-based bandwidth controller using eBPF metrics"""
    
    def __init__(self):
        # Load Kubernetes config
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.apps_v1 = client.AppsV1Api()
        self.monitor = eBPFMonitor()
        
        # Controller state
        self.smoothed_latency = None
        self.smoothed_jitter = None
        self.last_action_time = 0
        self.last_direction = None
        
        logger.info("ML Controller initialized")
        logger.info(f"Target: Jitter < {TARGET_JITTER_MS}ms, Latency < {TARGET_LATENCY_MS}ms")
    
    def start(self):
        """Start the control loop"""
        self.monitor.start()
        logger.info("Starting control loop...")
        
        while True:
            try:
                # Poll eBPF events
                self.monitor.poll_events(timeout_ms=1000)
                
                # Run control logic every CONTROL_INTERVAL_SEC
                time.sleep(CONTROL_INTERVAL_SEC)
                self._control_iteration()
                
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in control loop: {e}")
                time.sleep(5)
        
        self.monitor.stop()
    
    def _control_iteration(self):
        """Single control loop iteration"""
        # Get metrics from eBPF
        metrics = self.monitor.get_metrics()
        
        if metrics["sample_count"] == 0:
            logger.warning("No eBPF samples collected, skipping iteration")
            return
        
        # Combine TCP and UDP metrics (use worst case)
        raw_latency = max(
            metrics["tcp_latency_ms"] or 0,
            metrics["udp_latency_ms"] or 0
        )
        raw_jitter = max(
            metrics["tcp_jitter_ms"] or 0,
            metrics["udp_jitter_ms"] or 0
        )
        
        if raw_latency == 0:
            logger.warning("No valid latency measurements")
            return
        
        # EWMA smoothing
        if self.smoothed_latency is None:
            self.smoothed_latency = raw_latency
            self.smoothed_jitter = raw_jitter
        else:
            self.smoothed_latency = (EWMA_ALPHA * raw_latency + 
                                    (1 - EWMA_ALPHA) * self.smoothed_latency)
            self.smoothed_jitter = (EWMA_ALPHA * raw_jitter + 
                                   (1 - EWMA_ALPHA) * self.smoothed_jitter)
        
        logger.info(f"Metrics - TCP: {metrics['tcp_latency_ms']:.2f}ms/{metrics['tcp_jitter_ms']:.2f}ms, "
                   f"UDP: {metrics['udp_latency_ms']:.2f}ms/{metrics['udp_jitter_ms']:.2f}ms, "
                   f"Smoothed: {self.smoothed_latency:.2f}ms/{self.smoothed_jitter:.2f}ms, "
                   f"Samples: {metrics['sample_count']}")
        
        # Cooldown check
        time_since_last_action = time.time() - self.last_action_time
        if time_since_last_action < COOLDOWN_PERIOD_SEC:
            logger.info(f"In cooldown period ({time_since_last_action:.0f}s / {COOLDOWN_PERIOD_SEC}s)")
            return
        
        # Control decision
        action, bandwidth_change = self._decide_action(
            self.smoothed_latency, 
            self.smoothed_jitter
        )
        
        if action != "NO_ACTION":
            self._apply_bandwidth_change(bandwidth_change)
            self.last_action_time = time.time()
            self.last_direction = "decrease" if bandwidth_change < 0 else "increase"
            logger.info(f"Action: {action}, Bandwidth change: {bandwidth_change:+d} Mbps")
        
        # Clear samples for next iteration
        self.monitor.clear_samples()
    
    def _decide_action(self, latency, jitter):
        """Decide control action based on metrics"""
        if jitter > TARGET_JITTER_MS:
            # High jitter = congestion
            return "CONGESTION_THROTTLE", -AGGRESSIVE_DECREASE_MBPS
        
        elif latency > TARGET_LATENCY_MS and jitter <= TARGET_JITTER_MS:
            # High latency but low jitter = distance, not congestion
            return "LATENCY_GENTLE_THROTTLE", -GENTLE_DECREASE_MBPS
        
        else:
            # Metrics healthy, can increase
            return "INCREASE", INCREASE_STEP_MBPS
    
    def _apply_bandwidth_change(self, change_mbps):
        """Apply bandwidth change to best-effort deployments"""
        for deployment_name in BEST_EFFORT_DEPLOYMENTS:
            try:
                deployment = self.apps_v1.read_namespaced_deployment(
                    name=deployment_name,
                    namespace="default"
                )
                
                # Get current bandwidth
                annotations = deployment.spec.template.metadata.annotations or {}
                current_bw_str = annotations.get("kubernetes.io/egress-bandwidth", "1000M")
                current_bw = int(current_bw_str.rstrip("M"))
                
                # Calculate new bandwidth
                new_bw = max(MIN_BANDWIDTH_MBPS, 
                           min(MAX_BANDWIDTH_MBPS, current_bw + change_mbps))
                
                if new_bw == current_bw:
                    continue
                
                # Update annotation
                patch = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubernetes.io/egress-bandwidth": f"{new_bw}M"
                                }
                            }
                        }
                    }
                }
                
                self.apps_v1.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace="default",
                    body=patch
                )
                
                logger.info(f"Updated {deployment_name}: {current_bw}M -> {new_bw}M")
                
            except client.exceptions.ApiException as e:
                if e.status == 404:
                    logger.debug(f"Deployment {deployment_name} not found")
                else:
                    logger.error(f"Failed to update {deployment_name}: {e}")
            except Exception as e:
                logger.error(f"Error updating {deployment_name}: {e}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ML-Based QoS Controller with eBPF TCP/UDP Monitoring")
    logger.info("=" * 60)
    
    controller = MLController()
    controller.start()
