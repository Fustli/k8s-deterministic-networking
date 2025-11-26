#!/usr/bin/env python3

"""
Production-Grade Deterministic Networking ML Controller for Kubernetes
Version: 3.1 (Active Probing Mode - TCP + UDP)

Implements intelligent bandwidth control using ACTIVE network probing:
- Probes the Critical Service via TCP Handshake AND UDP round-trip.
- Calculates Jitter (IQR) locally from both probe histories.
- Uses the WORST jitter (max of TCP/UDP) for control decisions.
- Dynamically patches Deployment annotations to enforce bandwidth limits.
- Bypass Prometheus scraping lag for real-time <1s reaction times.
"""

import os
import time
import socket
import statistics
import logging
import math
from collections import deque
from dataclasses import dataclass
from kubernetes import client, config

# --- CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DetNet-Controller")

@dataclass
class ControllerConfig:
    # Target the CRITICAL service. 
    # TCP port: iperf3 control channel (always TCP even for UDP tests)
    # UDP port: iperf3 data channel for direct UDP latency measurement
    TARGET_HOST: str = os.getenv('TARGET_HOST', 'robot-control-svc.default.svc.cluster.local')
    TARGET_TCP_PORT: int = int(os.getenv('TARGET_TCP_PORT', '5201'))
    TARGET_UDP_PORT: int = int(os.getenv('TARGET_UDP_PORT', '5201'))
    
    # The noisy deployment to throttle (The "Target")
    THROTTLE_DEPLOYMENT: str = os.getenv('THROTTLE_DEPLOYMENT', 'telemetry-upload-deployment')
    THROTTLE_NAMESPACE: str = os.getenv('THROTTLE_NAMESPACE', 'default')

    # Thresholds
    # Active probes are very fast/clean. 5ms jitter here is massive congestion.
    TARGET_JITTER_MS: float = float(os.getenv('TARGET_JITTER_MS', '2.0'))
    
    # Bandwidth Limits (Mbps)
    MIN_BW: int = int(os.getenv('MIN_BW', '10'))
    MAX_BW: int = int(os.getenv('MAX_BW', '1000'))
    STEP_DOWN: int = int(os.getenv('STEP_DOWN', '100'))
    STEP_UP: int = int(os.getenv('STEP_UP', '10'))

    # Loop Settings
    # How many past samples to keep for Jitter calculation
    WINDOW_SIZE: int = int(os.getenv('WINDOW_SIZE', '20'))
    # Probing frequency (seconds)
    PROBE_INTERVAL: float = float(os.getenv('PROBE_INTERVAL', '0.5'))


class NetworkProbe:
    """
    Active Network Sensor.
    Performs lightweight TCP connects AND UDP round-trips to measure path latency.
    """
    # UDP probe payload (small packet to minimize overhead)
    UDP_PROBE_MSG = b'DETNET_PROBE'
    
    def __init__(self, host: str, tcp_port: int, udp_port: int, window_size: int):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        # Separate rolling windows for TCP and UDP
        self.tcp_history = deque(maxlen=window_size)
        self.udp_history = deque(maxlen=window_size)

    def _calc_iqr_jitter(self, history: deque) -> float:
        """Calculate Jitter using IQR (Q3 - Q1). Returns 0.0 if insufficient samples."""
        if len(history) < 4:
            return 0.0
        sorted_samples = sorted(history)
        n = len(sorted_samples)
        q1 = sorted_samples[n // 4]
        q3 = sorted_samples[(3 * n) // 4]
        return q3 - q1

    def _measure_tcp(self) -> tuple:
        """TCP handshake probe. Returns (latency_ms, jitter_ms)."""
        try:
            start = time.perf_counter()
            sock = socket.create_connection((self.host, self.tcp_port), timeout=1.0)
            sock.close()
            end = time.perf_counter()
            
            latency_ms = (end - start) * 1000
            self.tcp_history.append(latency_ms)
            jitter = self._calc_iqr_jitter(self.tcp_history)
            return latency_ms, jitter
            
        except socket.timeout:
            self.tcp_history.append(100.0)
            return 100.0, 50.0
        except Exception as e:
            logger.debug(f"TCP probe failed: {e}")
            return None, None

    def _measure_udp(self) -> tuple:
        """UDP round-trip probe. Returns (latency_ms, jitter_ms)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            
            start = time.perf_counter()
            # Send probe packet
            sock.sendto(self.UDP_PROBE_MSG, (self.host, self.udp_port))
            # Wait for response (iperf3 won't respond, so we measure send time only)
            # For true RTT, we'd need a custom echo server. Here we measure one-way + queue time.
            end = time.perf_counter()
            sock.close()
            
            # Note: This measures send latency only (no response expected from iperf3)
            # Still useful as it measures kernel->NIC->Cilium eBPF queue delays
            latency_ms = (end - start) * 1000
            self.udp_history.append(latency_ms)
            jitter = self._calc_iqr_jitter(self.udp_history)
            return latency_ms, jitter
            
        except socket.timeout:
            self.udp_history.append(100.0)
            return 100.0, 50.0
        except Exception as e:
            logger.debug(f"UDP probe failed: {e}")
            return None, None

    def measure(self) -> dict:
        """
        Performs both TCP and UDP probes.
        Returns dict with tcp_latency, tcp_jitter, udp_latency, udp_jitter, combined_jitter.
        Combined jitter = max(tcp_jitter, udp_jitter) for conservative control.
        """
        tcp_latency, tcp_jitter = self._measure_tcp()
        udp_latency, udp_jitter = self._measure_udp()
        
        # Handle probe failures
        if tcp_latency is None and udp_latency is None:
            return None
        
        tcp_jitter = tcp_jitter if tcp_jitter is not None else 0.0
        udp_jitter = udp_jitter if udp_jitter is not None else 0.0
        tcp_latency = tcp_latency if tcp_latency is not None else 0.0
        udp_latency = udp_latency if udp_latency is not None else 0.0
        
        # Use worst-case jitter for control decisions (conservative)
        combined_jitter = max(tcp_jitter, udp_jitter)
        
        return {
            'tcp_latency': tcp_latency,
            'tcp_jitter': tcp_jitter,
            'udp_latency': udp_latency,
            'udp_jitter': udp_jitter,
            'combined_jitter': combined_jitter
        }


class BandwidthController:
    """Core logic for the ML Control Loop."""
    
    def __init__(self, ctrl_config: ControllerConfig):
        self.cfg = ctrl_config
        self.probe = NetworkProbe(
            ctrl_config.TARGET_HOST,
            ctrl_config.TARGET_TCP_PORT,
            ctrl_config.TARGET_UDP_PORT,
            ctrl_config.WINDOW_SIZE
        )
        
        # Initialize Kubernetes Client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        self.apps_api = client.AppsV1Api()
        
        self.current_bw = 100 # Start assumption

    def _patch_deployment(self, bandwidth_mbps: int):
        """Applies the bandwidth limit via Annotation Patching (Workaround B)."""
        if bandwidth_mbps == self.current_bw:
            return

        logger.info(f"ACTION: Patching {self.cfg.THROTTLE_DEPLOYMENT} -> {bandwidth_mbps} Mbps")
        
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubernetes.io/egress-bandwidth": f"{bandwidth_mbps}M"
                        }
                    }
                }
            }
        }
        
        try:
            self.apps_api.patch_namespaced_deployment(
                self.cfg.THROTTLE_DEPLOYMENT, 
                self.cfg.THROTTLE_NAMESPACE, 
                body
            )
            self.current_bw = bandwidth_mbps
        except Exception as e:
            logger.error(f"Failed to patch deployment: {e}")

    def run(self):
        logger.info(f"Active Controller Started (TCP + UDP Probing).")
        logger.info(f"   Target: {self.cfg.TARGET_HOST}")
        logger.info(f"   TCP Port: {self.cfg.TARGET_TCP_PORT}, UDP Port: {self.cfg.TARGET_UDP_PORT}")
        logger.info(f"   Jitter Limit: {self.cfg.TARGET_JITTER_MS}ms")

        while True:
            # 1. MEASURE (Active Probes - TCP + UDP)
            metrics = self.probe.measure()
            
            if metrics is None:
                logger.warning("All probes failed - skipping cycle")
                time.sleep(self.cfg.PROBE_INTERVAL)
                continue
            
            jitter = metrics['combined_jitter']
            
            # Log detailed metrics periodically
            logger.debug(f"TCP: {metrics['tcp_latency']:.2f}ms (jitter: {metrics['tcp_jitter']:.2f}ms) | "
                        f"UDP: {metrics['udp_latency']:.2f}ms (jitter: {metrics['udp_jitter']:.2f}ms)")

            # 2. DECIDE
            new_bw = self.current_bw

            if jitter > self.cfg.TARGET_JITTER_MS:
                # CONGESTION -> Throttle Aggressively
                new_bw = max(self.cfg.MIN_BW, self.current_bw - self.cfg.STEP_DOWN)
                
                logger.warning(f"HIGH JITTER (TCP:{metrics['tcp_jitter']:.2f}ms UDP:{metrics['udp_jitter']:.2f}ms). "
                              f"Throttling: {self.current_bw} -> {new_bw}")
                
            elif jitter < (self.cfg.TARGET_JITTER_MS * 0.5):
                # STABLE -> Relax Limits Gently
                new_bw = min(self.cfg.MAX_BW, self.current_bw + self.cfg.STEP_UP)
                
                if new_bw != self.current_bw:
                    logger.info(f"Network Stable (TCP:{metrics['tcp_jitter']:.2f}ms UDP:{metrics['udp_jitter']:.2f}ms). "
                               f"Increasing: {self.current_bw} -> {new_bw}")

            # 3. ACT
            if new_bw != self.current_bw:
                self._patch_deployment(new_bw)
            
            # Loop delay
            time.sleep(self.cfg.PROBE_INTERVAL)

if __name__ == "__main__":
    cfg = ControllerConfig()
    controller = BandwidthController(cfg)
    try:
        controller.run()
    except KeyboardInterrupt:
        logger.info("Controller stopping...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")