#!/usr/bin/env python3
"""
Flow Manager Metrics Exporter for Prometheus
Exposes bandwidth limits AND real-time SLA metrics:
  - kubernetes_deployment_bandwidth_limit_mbps (from K8s annotations)
  - flowmanager_udp_jitter_ms (active UDP probe to robot-control)
  - flowmanager_tcp_throughput_mbps (TCP probe to safety-scanner)
  - flowmanager_best_effort_throughput_mbps (estimated from bandwidth limit)

These metrics power the Grafana dashboard panels.
"""

import os
import time
import socket
import threading
from collections import deque
from kubernetes import client, config
from prometheus_client import start_http_server, Gauge, Info
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [MetricsExporter] %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
ROBOT_CONTROL_HOST = os.getenv('ROBOT_CONTROL_HOST', 'robot-control-svc.default.svc.cluster.local')
ROBOT_CONTROL_PORT = int(os.getenv('ROBOT_CONTROL_PORT', '5201'))
SAFETY_SCANNER_HOST = os.getenv('SAFETY_SCANNER_HOST', 'safety-scanner-svc.default.svc.cluster.local')
SAFETY_SCANNER_PORT = int(os.getenv('SAFETY_SCANNER_PORT', '5202'))
PROBE_INTERVAL = float(os.getenv('PROBE_INTERVAL', '1.0'))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '20'))

# --- PROMETHEUS METRICS ---
# Bandwidth limit from K8s annotations
bandwidth_limit = Gauge(
    'kubernetes_deployment_bandwidth_limit_mbps',
    'Current egress bandwidth limit in Mbps',
    ['namespace', 'deployment']
)

# UDP Jitter metric (for Panel 1)
udp_jitter_gauge = Gauge(
    'flowmanager_udp_jitter_ms',
    'UDP jitter to critical service (IQR-based)',
    ['service', 'target_host']
)

# UDP Latency metric
udp_latency_gauge = Gauge(
    'flowmanager_udp_latency_ms',
    'UDP probe latency to critical service',
    ['service', 'target_host']
)

# TCP Throughput metric (for Panel 2) - estimated from connection success rate
tcp_throughput_gauge = Gauge(
    'flowmanager_tcp_throughput_mbps',
    'Estimated TCP throughput to critical service',
    ['service', 'target_host']
)

# TCP Latency metric
tcp_latency_gauge = Gauge(
    'flowmanager_tcp_latency_ms',
    'TCP connection latency to critical service',
    ['service', 'target_host']
)

# Best-effort actual throughput (for Panel 4)
best_effort_throughput_gauge = Gauge(
    'flowmanager_best_effort_throughput_mbps',
    'Estimated actual throughput of best-effort traffic',
    ['deployment']
)

# Controller info
controller_info = Info(
    'flowmanager_controller',
    'Flow Manager controller configuration'
)


class UDPProbe:
    """Active UDP probe for jitter measurement using IQR."""
    
    UDP_PROBE_MSG = b'METRICS_PROBE'
    
    def __init__(self, host: str, port: int, window_size: int = 20):
        self.host = host
        self.port = port
        self.latency_history = deque(maxlen=window_size)
        self._resolved_ip = None
        
    def _resolve_host(self):
        if self._resolved_ip:
            return self._resolved_ip
        try:
            self._resolved_ip = socket.gethostbyname(self.host)
            return self._resolved_ip
        except socket.gaierror as e:
            logger.warning(f"DNS resolution failed for {self.host}: {e}")
            return None
    
    def _calc_iqr_jitter(self):
        """Calculate jitter using IQR (Q3 - Q1)."""
        if len(self.latency_history) < 4:
            return 0.0
        sorted_samples = sorted(self.latency_history)
        n = len(sorted_samples)
        q1 = sorted_samples[n // 4]
        q3 = sorted_samples[(3 * n) // 4]
        return q3 - q1

    def measure(self):
        """Perform UDP probe and return latency/jitter."""
        target_ip = self._resolve_host()
        if not target_ip:
            return {'latency_ms': 100.0, 'jitter_ms': 50.0, 'status': 'dns_failure'}
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            
            start = time.perf_counter()
            sock.sendto(self.UDP_PROBE_MSG, (target_ip, self.port))
            end = time.perf_counter()
            sock.close()
            
            latency_ms = (end - start) * 1000
            self.latency_history.append(latency_ms)
            jitter_ms = self._calc_iqr_jitter()
            
            return {
                'latency_ms': latency_ms,
                'jitter_ms': jitter_ms,
                'status': 'ok'
            }
            
        except socket.timeout:
            self.latency_history.append(100.0)
            return {'latency_ms': 100.0, 'jitter_ms': self._calc_iqr_jitter(), 'status': 'timeout'}
        except Exception as e:
            logger.debug(f"UDP probe failed: {e}")
            return {'latency_ms': 0.0, 'jitter_ms': 0.0, 'status': 'error'}


class TCPProbe:
    """TCP connection probe for throughput estimation."""
    
    def __init__(self, host: str, port: int, window_size: int = 20):
        self.host = host
        self.port = port
        self.latency_history = deque(maxlen=window_size)
        self.success_count = 0
        self.total_count = 0
        
    def _calc_iqr_jitter(self):
        if len(self.latency_history) < 4:
            return 0.0
        sorted_samples = sorted(self.latency_history)
        n = len(sorted_samples)
        q1 = sorted_samples[n // 4]
        q3 = sorted_samples[(3 * n) // 4]
        return q3 - q1

    def measure(self):
        """Perform TCP connection probe."""
        self.total_count += 1
        
        try:
            start = time.perf_counter()
            sock = socket.create_connection((self.host, self.port), timeout=2.0)
            sock.close()
            end = time.perf_counter()
            
            latency_ms = (end - start) * 1000
            self.latency_history.append(latency_ms)
            self.success_count += 1
            
            # Estimate throughput based on latency and success rate
            # Lower latency = higher potential throughput
            # Base throughput of 100Mbps, reduced by latency factor
            success_rate = self.success_count / max(self.total_count, 1)
            latency_factor = max(0.1, 1.0 - (latency_ms / 100.0))
            estimated_throughput = 100.0 * success_rate * latency_factor
            
            return {
                'latency_ms': latency_ms,
                'jitter_ms': self._calc_iqr_jitter(),
                'throughput_mbps': estimated_throughput,
                'status': 'ok'
            }
            
        except socket.timeout:
            self.latency_history.append(100.0)
            return {
                'latency_ms': 100.0,
                'jitter_ms': self._calc_iqr_jitter(),
                'throughput_mbps': 0.0,
                'status': 'timeout'
            }
        except ConnectionRefusedError:
            return {
                'latency_ms': 0.0,
                'jitter_ms': 0.0,
                'throughput_mbps': 0.0,
                'status': 'refused'
            }
        except Exception as e:
            logger.debug(f"TCP probe failed: {e}")
            return {
                'latency_ms': 0.0,
                'jitter_ms': 0.0,
                'throughput_mbps': 0.0,
                'status': 'error'
            }


class MetricsCollector:
    """Collects all metrics for the Flow Manager dashboard."""
    
    def __init__(self):
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        
        self.v1 = client.AppsV1Api()
        
        # Initialize probes
        self.udp_probe = UDPProbe(ROBOT_CONTROL_HOST, ROBOT_CONTROL_PORT, WINDOW_SIZE)
        self.tcp_probe = TCPProbe(SAFETY_SCANNER_HOST, SAFETY_SCANNER_PORT, WINDOW_SIZE)
        
        # Set controller info
        controller_info.info({
            'robot_control_host': ROBOT_CONTROL_HOST,
            'robot_control_port': str(ROBOT_CONTROL_PORT),
            'safety_scanner_host': SAFETY_SCANNER_HOST,
            'safety_scanner_port': str(SAFETY_SCANNER_PORT),
            'version': '2.0'
        })
        
    def collect_bandwidth_limits(self):
        """Query all deployments and extract bandwidth annotations."""
        try:
            deployments = self.v1.list_namespaced_deployment(namespace='default')
            
            for dep in deployments.items:
                if dep.spec.template.metadata.annotations:
                    bw_annotation = dep.spec.template.metadata.annotations.get('kubernetes.io/egress-bandwidth')
                    if bw_annotation:
                        # Parse bandwidth (e.g., "385M" -> 385)
                        bw_mbps = int(bw_annotation.rstrip('MmKkGg'))
                        
                        bandwidth_limit.labels(
                            namespace=dep.metadata.namespace,
                            deployment=dep.metadata.name
                        ).set(bw_mbps)
                        
                        # Estimate best-effort actual throughput
                        # Assume actual throughput is ~80% of limit when active
                        if 'telemetry' in dep.metadata.name or 'erp' in dep.metadata.name:
                            estimated_actual = min(bw_mbps * 0.8, bw_mbps)
                            best_effort_throughput_gauge.labels(
                                deployment=dep.metadata.name
                            ).set(estimated_actual)
        
        except Exception as e:
            logger.error(f"Error collecting bandwidth metrics: {e}")

    def collect_probe_metrics(self):
        """Run active probes and update metrics."""
        # UDP Probe to robot-control
        udp_result = self.udp_probe.measure()
        if udp_result['status'] in ['ok', 'timeout']:
            udp_jitter_gauge.labels(
                service='robot-control',
                target_host=ROBOT_CONTROL_HOST
            ).set(udp_result['jitter_ms'])
            
            udp_latency_gauge.labels(
                service='robot-control',
                target_host=ROBOT_CONTROL_HOST
            ).set(udp_result['latency_ms'])
        
        # TCP Probe to safety-scanner
        tcp_result = self.tcp_probe.measure()
        if tcp_result['status'] in ['ok', 'timeout']:
            tcp_throughput_gauge.labels(
                service='safety-scanner',
                target_host=SAFETY_SCANNER_HOST
            ).set(tcp_result['throughput_mbps'])
            
            tcp_latency_gauge.labels(
                service='safety-scanner',
                target_host=SAFETY_SCANNER_HOST
            ).set(tcp_result['latency_ms'])

    def run_collection_loop(self):
        """Main collection loop."""
        while True:
            try:
                self.collect_bandwidth_limits()
                self.collect_probe_metrics()
            except Exception as e:
                logger.error(f"Collection error: {e}")
            
            time.sleep(PROBE_INTERVAL)


def main():
    """Start the metrics exporter."""
    logger.info("=" * 60)
    logger.info("Flow Manager Metrics Exporter Starting")
    logger.info("=" * 60)
    logger.info(f"  Robot Control: {ROBOT_CONTROL_HOST}:{ROBOT_CONTROL_PORT}")
    logger.info(f"  Safety Scanner: {SAFETY_SCANNER_HOST}:{SAFETY_SCANNER_PORT}")
    logger.info(f"  Probe Interval: {PROBE_INTERVAL}s")
    logger.info("=" * 60)
    
    # Start Prometheus HTTP server on port 8000
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")
    
    # Start collection
    collector = MetricsCollector()
    collector.run_collection_loop()


if __name__ == '__main__':
    main()
