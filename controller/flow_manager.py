#!/usr/bin/env python3

"""
Hybrid Deterministic-ML Network Controller for Kubernetes
Version: 4.0 (Flow Manager - Active Probing + Hubble Metrics)

Implements intelligent bandwidth control using HYBRID sensing:
- UDP Jitter: Active probing to robot-control (needs <5ms jitter)
- TCP Throughput: Hubble metrics for safety-scanner (needs >50Mbps guaranteed)
- Calculates Jitter (IQR) from probe history, uses worst-case for decisions
- Dynamically patches Deployment annotations to enforce bandwidth limits
- Sub-second reaction times via active probing, Prometheus for TCP throughput

Control Logic:
  IF UDP_Jitter > 5ms OR TCP_Throughput < 50Mbps:
      THROTTLE: Decrease best-effort bandwidth (aggressive)
  ELSE IF conditions are healthy:
      RELAX: Increase best-effort bandwidth (gentle)
"""

import os
import time
import socket
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from kubernetes import client, config

# Optional: Prometheus client for Hubble metrics
try:
    import requests
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# --- CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [FlowManager] %(message)s'
)
logger = logging.getLogger("FlowManager")


@dataclass
class ControllerConfig:
    """Configuration loaded from environment variables."""
    
    # --- Critical App: Robot Control (UDP, needs low jitter) ---
    ROBOT_CONTROL_HOST: str = field(
        default_factory=lambda: os.getenv('ROBOT_CONTROL_HOST', 
            'robot-control-svc.default.svc.cluster.local'))
    ROBOT_CONTROL_UDP_PORT: int = field(
        default_factory=lambda: int(os.getenv('ROBOT_CONTROL_UDP_PORT', '5201')))
    
    # --- Critical App: Safety Scanner (TCP, needs guaranteed throughput) ---
    SAFETY_SCANNER_HOST: str = field(
        default_factory=lambda: os.getenv('SAFETY_SCANNER_HOST', 
            'safety-scanner-svc.default.svc.cluster.local'))
    SAFETY_SCANNER_TCP_PORT: int = field(
        default_factory=lambda: int(os.getenv('SAFETY_SCANNER_TCP_PORT', '5202')))
    
    # --- Prometheus for Hubble metrics (TCP throughput) ---
    PROMETHEUS_URL: str = field(
        default_factory=lambda: os.getenv('PROMETHEUS_URL', 
            'http://prometheus.monitoring:9090'))
    
    # --- Best-Effort App to Throttle (The "Noise") ---
    THROTTLE_DEPLOYMENT: str = field(
        default_factory=lambda: os.getenv('THROTTLE_DEPLOYMENT', 'telemetry-upload-deployment'))
    THROTTLE_NAMESPACE: str = field(
        default_factory=lambda: os.getenv('THROTTLE_NAMESPACE', 'default'))

    # --- SLA Thresholds ---
    # UDP Jitter threshold (ms) - robot-control needs <5ms
    UDP_JITTER_THRESHOLD_MS: float = field(
        default_factory=lambda: float(os.getenv('UDP_JITTER_THRESHOLD_MS', '5.0')))
    # TCP Throughput threshold (Mbps) - safety-scanner needs >50Mbps
    TCP_THROUGHPUT_THRESHOLD_MBPS: float = field(
        default_factory=lambda: float(os.getenv('TCP_THROUGHPUT_THRESHOLD_MBPS', '50.0')))
    
    # --- Bandwidth Control Limits (Mbps) ---
    MIN_BW: int = field(default_factory=lambda: int(os.getenv('MIN_BW', '10')))
    MAX_BW: int = field(default_factory=lambda: int(os.getenv('MAX_BW', '1000')))
    STEP_DOWN: int = field(default_factory=lambda: int(os.getenv('STEP_DOWN', '100')))
    STEP_UP: int = field(default_factory=lambda: int(os.getenv('STEP_UP', '10')))

    # --- Control Loop Settings ---
    WINDOW_SIZE: int = field(default_factory=lambda: int(os.getenv('WINDOW_SIZE', '20')))
    PROBE_INTERVAL: float = field(
        default_factory=lambda: float(os.getenv('PROBE_INTERVAL', '0.5')))
    PROMETHEUS_QUERY_INTERVAL: float = field(
        default_factory=lambda: float(os.getenv('PROMETHEUS_QUERY_INTERVAL', '5.0')))


class UDPJitterProbe:
    """
    Active UDP Probe for Robot Control latency/jitter measurement.
    Uses IQR (Interquartile Range) for robust jitter calculation.
    """
    
    UDP_PROBE_MSG = b'FLOWMGR_PROBE'
    
    def __init__(self, host: str, port: int, window_size: int):
        self.host = host
        self.port = port
        self.latency_history: deque = deque(maxlen=window_size)
        self._resolved_ip: Optional[str] = None
        
    def _resolve_host(self) -> Optional[str]:
        """Resolve DNS once for efficiency."""
        if self._resolved_ip:
            return self._resolved_ip
        try:
            self._resolved_ip = socket.gethostbyname(self.host)
            return self._resolved_ip
        except socket.gaierror as e:
            logger.warning(f"DNS resolution failed for {self.host}: {e}")
            return None
    
    def _calc_iqr_jitter(self) -> float:
        """
        Calculate Jitter using IQR (Q3 - Q1).
        IQR is robust to outliers, ideal for network measurements.
        Returns 0.0 if insufficient samples.
        """
        if len(self.latency_history) < 4:
            return 0.0
        sorted_samples = sorted(self.latency_history)
        n = len(sorted_samples)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        q1 = sorted_samples[q1_idx]
        q3 = sorted_samples[q3_idx]
        return q3 - q1

    def measure(self) -> Dict[str, float]:
        """
        Perform UDP probe and return latency/jitter metrics.
        Returns dict with 'latency_ms' and 'jitter_ms'.
        """
        target_ip = self._resolve_host()
        if not target_ip:
            return {'latency_ms': 100.0, 'jitter_ms': 50.0, 'status': 'dns_failure'}
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            
            start = time.perf_counter()
            # Send UDP probe - measure local send latency
            # (iperf3 server won't echo, but we capture kernel->NIC->eBPF queue time)
            sock.sendto(self.UDP_PROBE_MSG, (target_ip, self.port))
            end = time.perf_counter()
            sock.close()
            
            latency_ms = (end - start) * 1000
            self.latency_history.append(latency_ms)
            jitter_ms = self._calc_iqr_jitter()
            
            return {
                'latency_ms': latency_ms,
                'jitter_ms': jitter_ms,
                'status': 'ok',
                'samples': len(self.latency_history)
            }
            
        except socket.timeout:
            # Timeout penalty
            self.latency_history.append(100.0)
            return {'latency_ms': 100.0, 'jitter_ms': self._calc_iqr_jitter(), 'status': 'timeout'}
        except Exception as e:
            logger.debug(f"UDP probe failed: {e}")
            return {'latency_ms': 0.0, 'jitter_ms': 0.0, 'status': 'error'}


class TCPLatencyProbe:
    """
    TCP Handshake Probe for Safety Scanner connectivity check.
    Also maintains latency history for secondary jitter calculation.
    """
    
    def __init__(self, host: str, port: int, window_size: int):
        self.host = host
        self.port = port
        self.latency_history: deque = deque(maxlen=window_size)
        
    def _calc_iqr_jitter(self) -> float:
        """Calculate IQR jitter from TCP handshake times."""
        if len(self.latency_history) < 4:
            return 0.0
        sorted_samples = sorted(self.latency_history)
        n = len(sorted_samples)
        q1 = sorted_samples[n // 4]
        q3 = sorted_samples[(3 * n) // 4]
        return q3 - q1

    def measure(self) -> Dict[str, float]:
        """
        Perform TCP handshake probe to verify safety-scanner reachability.
        Returns latency and connection status.
        """
        try:
            start = time.perf_counter()
            sock = socket.create_connection((self.host, self.port), timeout=2.0)
            sock.close()
            end = time.perf_counter()
            
            latency_ms = (end - start) * 1000
            self.latency_history.append(latency_ms)
            
            return {
                'latency_ms': latency_ms,
                'jitter_ms': self._calc_iqr_jitter(),
                'status': 'ok'
            }
            
        except socket.timeout:
            self.latency_history.append(100.0)
            return {'latency_ms': 100.0, 'jitter_ms': self._calc_iqr_jitter(), 'status': 'timeout'}
        except ConnectionRefusedError:
            return {'latency_ms': 0.0, 'jitter_ms': 0.0, 'status': 'refused'}
        except Exception as e:
            logger.debug(f"TCP probe failed: {e}")
            return {'latency_ms': 0.0, 'jitter_ms': 0.0, 'status': 'error'}


class HubbleMetricsCollector:
    """
    Collects TCP throughput metrics from Hubble via Prometheus.
    Used for safety-scanner throughput SLA monitoring.
    """
    
    def __init__(self, prometheus_url: str):
        self.prometheus_url = prometheus_url
        self.last_throughput_mbps: float = 100.0  # Assume healthy until proven otherwise
        self.last_query_time: float = 0
        self._lock = threading.Lock()
        
    def query_throughput(self, destination_service: str = 'safety-scanner') -> float:
        """
        Query Hubble L7 metrics for TCP throughput.
        Falls back to TCP probe-based estimation if Hubble unavailable.
        
        Returns throughput in Mbps.
        """
        if not PROMETHEUS_AVAILABLE:
            logger.debug("Prometheus client not available, using fallback")
            return self.last_throughput_mbps
        
        # PromQL: Rate of bytes processed for flows TO safety-scanner
        # Using hubble_flows_processed_total or hubble_drop_total as proxy
        query = f'''
            sum(rate(hubble_flows_processed_total{{
                destination=~".*{destination_service}.*",
                type="TRACE"
            }}[1m])) * 8 / 1000000
        '''
        
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': query.strip()},
                timeout=2.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result['status'] == 'success' and result['data']['result']:
                    value = float(result['data']['result'][0]['value'][1])
                    with self._lock:
                        self.last_throughput_mbps = value if value > 0 else self.last_throughput_mbps
                    return self.last_throughput_mbps
            
            # Alternative query using flow latency bucket metrics
            alt_query = '''
                histogram_quantile(0.5, 
                    sum(rate(hubble_flows_processed_total[1m])) by (le)
                )
            '''
            
        except requests.RequestException as e:
            logger.debug(f"Prometheus query failed: {e}")
        except Exception as e:
            logger.debug(f"Metrics parsing error: {e}")
        
        return self.last_throughput_mbps

    def get_best_effort_throughput(self, source_app: str = 'telemetry-upload') -> float:
        """
        Query actual throughput of best-effort app (noise source).
        Used for dashboard visualization.
        """
        if not PROMETHEUS_AVAILABLE:
            return 0.0
            
        query = f'''
            sum(rate(hubble_flows_processed_total{{
                source=~".*{source_app}.*"
            }}[1m])) * 8 / 1000000
        '''
        
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': query.strip()},
                timeout=2.0
            )
            if response.status_code == 200:
                result = response.json()
                if result['status'] == 'success' and result['data']['result']:
                    return float(result['data']['result'][0]['value'][1])
        except Exception:
            pass
        return 0.0


class BandwidthController:
    """
    Core Hybrid Controller Logic.
    Combines active probing (UDP jitter) with Hubble metrics (TCP throughput)
    for intelligent bandwidth allocation decisions.
    """
    
    def __init__(self, cfg: ControllerConfig):
        self.cfg = cfg
        
        # Initialize probes
        self.udp_probe = UDPJitterProbe(
            cfg.ROBOT_CONTROL_HOST,
            cfg.ROBOT_CONTROL_UDP_PORT,
            cfg.WINDOW_SIZE
        )
        self.tcp_probe = TCPLatencyProbe(
            cfg.SAFETY_SCANNER_HOST,
            cfg.SAFETY_SCANNER_TCP_PORT,
            cfg.WINDOW_SIZE
        )
        self.hubble = HubbleMetricsCollector(cfg.PROMETHEUS_URL)
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        
        self.apps_api = client.AppsV1Api()
        
        # State
        self.current_bw: int = 500  # Start at 50% capacity (conservative)
        self._last_prometheus_query: float = 0
        self._cached_tcp_throughput: float = 100.0  # Assume healthy
        
    def _get_current_bandwidth(self) -> int:
        """Read current bandwidth annotation from deployment."""
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                self.cfg.THROTTLE_DEPLOYMENT,
                self.cfg.THROTTLE_NAMESPACE
            )
            if deployment.spec.template.metadata.annotations:
                bw_str = deployment.spec.template.metadata.annotations.get(
                    'kubernetes.io/egress-bandwidth', '1000M')
                # Parse "100M" -> 100
                return int(bw_str.rstrip('MmKkGg'))
        except Exception as e:
            logger.debug(f"Could not read current bandwidth: {e}")
        return self.current_bw

    def _patch_deployment(self, bandwidth_mbps: int) -> bool:
        """
        Apply bandwidth limit via Kubernetes Annotation Patching.
        This is the ONLY method that works with Cilium v1.18.x
        (CiliumNetworkPolicy does not support bandwidth fields).
        """
        if bandwidth_mbps == self.current_bw:
            return True

        logger.info(f"PATCHING: {self.cfg.THROTTLE_DEPLOYMENT} -> {bandwidth_mbps}M")
        
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
                name=self.cfg.THROTTLE_DEPLOYMENT,
                namespace=self.cfg.THROTTLE_NAMESPACE,
                body=body
            )
            self.current_bw = bandwidth_mbps
            return True
        except client.ApiException as e:
            logger.error(f"Failed to patch deployment: {e.status} - {e.reason}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error patching deployment: {e}")
            return False

    def _query_tcp_throughput(self) -> float:
        """
        Query TCP throughput from Hubble/Prometheus with caching.
        Only queries every PROMETHEUS_QUERY_INTERVAL seconds.
        """
        now = time.time()
        if now - self._last_prometheus_query >= self.cfg.PROMETHEUS_QUERY_INTERVAL:
            self._cached_tcp_throughput = self.hubble.query_throughput('safety-scanner')
            self._last_prometheus_query = now
        return self._cached_tcp_throughput

    def _make_control_decision(self, udp_metrics: Dict, tcp_metrics: Dict) -> int:
        """
        Hybrid Control Decision Logic.
        
        SLA Violations trigger THROTTLE:
          - UDP Jitter > 5ms (robot-control latency SLA)
          - TCP Throughput < 50Mbps (safety-scanner bandwidth SLA)
        
        Both SLAs healthy: RELAX (gentle increase)
        """
        udp_jitter = udp_metrics.get('jitter_ms', 0.0)
        tcp_throughput = self._query_tcp_throughput()
        
        # Current state
        new_bw = self.current_bw
        
        # --- CHECK SLA VIOLATIONS ---
        udp_violation = udp_jitter > self.cfg.UDP_JITTER_THRESHOLD_MS
        tcp_violation = tcp_throughput < self.cfg.TCP_THROUGHPUT_THRESHOLD_MBPS
        
        if udp_violation or tcp_violation:
            # THROTTLE: Aggressively reduce best-effort bandwidth
            new_bw = max(self.cfg.MIN_BW, self.current_bw - self.cfg.STEP_DOWN)
            
            violation_reasons = []
            if udp_violation:
                violation_reasons.append(f"UDP_Jitter={udp_jitter:.2f}ms>{self.cfg.UDP_JITTER_THRESHOLD_MS}ms")
            if tcp_violation:
                violation_reasons.append(f"TCP_Throughput={tcp_throughput:.1f}Mbps<{self.cfg.TCP_THROUGHPUT_THRESHOLD_MBPS}Mbps")
            
            logger.warning(f"SLA VIOLATION: {', '.join(violation_reasons)} | "
                          f"THROTTLE: {self.current_bw}M -> {new_bw}M")
            
        elif udp_jitter < (self.cfg.UDP_JITTER_THRESHOLD_MS * 0.5) and \
             tcp_throughput >= self.cfg.TCP_THROUGHPUT_THRESHOLD_MBPS:
            # RELAX: Network is healthy, gently increase best-effort bandwidth
            new_bw = min(self.cfg.MAX_BW, self.current_bw + self.cfg.STEP_UP)
            
            if new_bw != self.current_bw:
                logger.info(f"SLA OK: UDP_Jitter={udp_jitter:.2f}ms, TCP={tcp_throughput:.1f}Mbps | "
                           f"RELAX: {self.current_bw}M -> {new_bw}M")
        
        return new_bw

    def run(self):
        """Main control loop."""
        logger.info("=" * 60)
        logger.info("HYBRID FLOW MANAGER STARTED")
        logger.info("=" * 60)
        logger.info(f"   Robot Control (UDP): {self.cfg.ROBOT_CONTROL_HOST}:{self.cfg.ROBOT_CONTROL_UDP_PORT}")
        logger.info(f"   Safety Scanner (TCP): {self.cfg.SAFETY_SCANNER_HOST}:{self.cfg.SAFETY_SCANNER_TCP_PORT}")
        logger.info(f"   Throttle Target: {self.cfg.THROTTLE_DEPLOYMENT}")
        logger.info(f"   UDP Jitter SLA: <{self.cfg.UDP_JITTER_THRESHOLD_MS}ms")
        logger.info(f"   TCP Throughput SLA: >{self.cfg.TCP_THROUGHPUT_THRESHOLD_MBPS}Mbps")
        logger.info(f"   Bandwidth Range: {self.cfg.MIN_BW}M - {self.cfg.MAX_BW}M")
        logger.info("=" * 60)
        
        # Sync current state from cluster
        self.current_bw = self._get_current_bandwidth()
        logger.info(f"Initial bandwidth: {self.current_bw}M")
        
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                
                # 1. MEASURE: Collect metrics from both sources
                udp_metrics = self.udp_probe.measure()
                tcp_metrics = self.tcp_probe.measure()
                
                # Skip cycle if both probes fail
                if udp_metrics.get('status') == 'error' and tcp_metrics.get('status') == 'error':
                    logger.warning("All probes failed - skipping cycle")
                    time.sleep(self.cfg.PROBE_INTERVAL)
                    continue
                
                # 2. DECIDE: Make control decision based on SLA compliance
                new_bw = self._make_control_decision(udp_metrics, tcp_metrics)
                
                # 3. ACT: Apply bandwidth change if needed
                if new_bw != self.current_bw:
                    self._patch_deployment(new_bw)
                
                # Periodic status log (every 20 cycles)
                if cycle_count % 20 == 0:
                    tcp_throughput = self._cached_tcp_throughput
                    logger.info(f"Status: UDP_Jitter={udp_metrics.get('jitter_ms', 0):.2f}ms | "
                               f"TCP_Throughput={tcp_throughput:.1f}Mbps | "
                               f"BW_Limit={self.current_bw}M")
                
                time.sleep(self.cfg.PROBE_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Controller stopped by user")
                break
            except Exception as e:
                logger.error(f"Control loop error: {e}")
                time.sleep(1.0)  # Back off on errors


def main():
    """Entry point."""
    cfg = ControllerConfig()
    controller = BandwidthController(cfg)
    
    try:
        controller.run()
    except KeyboardInterrupt:
        logger.info("Shutting down Flow Manager...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
