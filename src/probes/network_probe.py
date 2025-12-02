#!/usr/bin/env python3
"""
Dedicated Network Probe Exporter
Continuously measures ICMP ping and TCP handshake latency (RAW DATA ONLY)
Exports raw latency measurements via Prometheus for consumption by flow_manager
Flow manager is responsible for all jitter calculations and control decisions
"""

import socket
import time
import logging
import os
import struct
from dataclasses import dataclass
from typing import Optional, List
from prometheus_client import start_http_server, Gauge, Histogram

# Configuration
ROBOT_CONTROL_HOST = os.getenv("ROBOT_CONTROL_HOST", "robot-control-svc.default.svc.cluster.local")
ROBOT_CONTROL_UDP_PORT = int(os.getenv("ROBOT_CONTROL_UDP_PORT", "5201"))  # UDP reflector
SAFETY_SCANNER_HOST = os.getenv("SAFETY_SCANNER_HOST", "safety-scanner-svc.default.svc.cluster.local")
SAFETY_SCANNER_TCP_PORT = int(os.getenv("SAFETY_SCANNER_TCP_PORT", "5202"))  # TCP service
PROBE_INTERVAL = float(os.getenv("PROBE_INTERVAL", "0.5"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus Metrics - RAW MEASUREMENTS ONLY
tcp_latency_gauge = Gauge('network_probe_tcp_latency_ms', 'TCP handshake latency in milliseconds', ['target'])
tcp_success_gauge = Gauge('network_probe_tcp_success', 'TCP probe success (1=success, 0=failure)', ['target'])
tcp_throughput_gauge = Gauge('network_probe_tcp_throughput_mbps', 'TCP throughput in Mbps', ['target'])

udp_latency_gauge = Gauge('network_probe_udp_latency_ms', 'UDP round-trip latency in milliseconds', ['target'])
udp_success_gauge = Gauge('network_probe_udp_success', 'UDP probe success (1=success, 0=failure)', ['target'])

icmp_latency_gauge = Gauge('network_probe_icmp_latency_ms', 'ICMP ping latency in milliseconds', ['target'])
icmp_success_gauge = Gauge('network_probe_icmp_success', 'ICMP probe success (1=success, 0=failure)', ['target'])

# Histogram for distribution analysis
tcp_latency_hist = Histogram('network_probe_tcp_latency_hist', 'TCP latency histogram', ['target'], 
                              buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0])
udp_latency_hist = Histogram('network_probe_udp_latency_hist', 'UDP latency histogram', ['target'],
                              buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0])
icmp_latency_hist = Histogram('network_probe_icmp_latency_hist', 'ICMP latency histogram', ['target'],
                               buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0])


@dataclass
class ProbeResult:
    """Single probe measurement result"""
    latency_ms: Optional[float]
    success: bool
    timestamp: float


class NetworkProbe:
    """Measures TCP handshake, UDP RTT, and TCP throughput - RAW DATA ONLY"""
    
    def __init__(self, robot_control_host: str, robot_control_udp_port: int,
                 safety_scanner_host: str, safety_scanner_tcp_port: int):
        # Robot control (UDP)
        self.robot_control_host = robot_control_host
        self.robot_control_udp_port = robot_control_udp_port
        
        # Safety scanner (TCP)
        self.safety_scanner_host = safety_scanner_host
        self.safety_scanner_tcp_port = safety_scanner_tcp_port
        
        # Resolve targets
        try:
            self.robot_control_ip = socket.gethostbyname(robot_control_host)
            logger.info(f"Resolved robot-control: {robot_control_host} -> {self.robot_control_ip}")
        except Exception as e:
            logger.error(f"Failed to resolve {robot_control_host}: {e}")
            self.robot_control_ip = robot_control_host
        
        try:
            self.safety_scanner_ip = socket.gethostbyname(safety_scanner_host)
            logger.info(f"Resolved safety-scanner: {safety_scanner_host} -> {self.safety_scanner_ip}")
        except Exception as e:
            logger.error(f"Failed to resolve {safety_scanner_host}: {e}")
            self.safety_scanner_ip = safety_scanner_host
        
        # Try to create raw ICMP socket (needs CAP_NET_RAW)
        self.icmp_enabled = self._check_icmp_capability()
    
    def _check_icmp_capability(self) -> bool:
        """Check if we have capability to send raw ICMP packets"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.close()
            logger.info("Raw ICMP socket capability available")
            return True
        except PermissionError:
            logger.warning("WARNING: No CAP_NET_RAW - ICMP probing disabled (use TCP only)")
            return False
        except Exception as e:
            logger.error(f"ICMP capability check failed: {e}")
            return False
    
    def measure_tcp_handshake(self) -> ProbeResult:
        """Measure TCP 3-way handshake latency to safety-scanner"""
        start = time.perf_counter()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((self.safety_scanner_ip, self.safety_scanner_tcp_port))
            latency_ms = (time.perf_counter() - start) * 1000
            sock.close()
            return ProbeResult(latency_ms=latency_ms, success=True, timestamp=time.time())
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(f"TCP probe failed: {e} (took {latency_ms:.2f}ms)")
            return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
    
    def measure_icmp_ping(self) -> ProbeResult:
        """Measure ICMP echo request/reply RTT using raw socket"""
        if not self.icmp_enabled:
            return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
        
        try:
            # Create raw ICMP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.settimeout(1.0)
            
            # Build ICMP Echo Request packet
            icmp_id = os.getpid() & 0xFFFF
            icmp_seq = 1
            
            # ICMP header: type=8 (echo request), code=0, checksum=0 (placeholder), id, seq
            header = self._create_icmp_packet(icmp_id, icmp_seq)
            
            start = time.perf_counter()
            sock.sendto(header, (self.target_ip, 0))
            
            # Wait for echo reply
            sock.recvfrom(1024)  # ICMP Echo Reply
            latency_ms = (time.perf_counter() - start) * 1000
            
            sock.close()
            return ProbeResult(latency_ms=latency_ms, success=True, timestamp=time.time())
            
        except socket.timeout:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(f"ICMP probe timeout (took {latency_ms:.2f}ms)")
            return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
        except Exception as e:
            logger.debug(f"ICMP probe error: {e}")
            return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
    
    def measure_udp_rtt(self, count: int = 10) -> ProbeResult:
        """Measure UDP round-trip time to robot-control reflector"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.2)  # 200ms timeout per probe
            
            latencies = []
            for _ in range(count):
                # Send timestamped packet
                send_time = time.perf_counter()
                payload = struct.pack('d', send_time)
                sock.sendto(payload, (self.robot_control_ip, self.robot_control_udp_port))
                
                try:
                    data, _ = sock.recvfrom(1024)
                    recv_time = time.perf_counter()
                    latency_ms = (recv_time - send_time) * 1000
                    latencies.append(latency_ms)
                except socket.timeout:
                    logger.debug(f"UDP probe timeout")
                    continue
            
            sock.close()
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                return ProbeResult(latency_ms=avg_latency, success=True, timestamp=time.time())
            else:
                return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
                
        except Exception as e:
            logger.error(f"UDP probe error: {e}")
            return ProbeResult(latency_ms=None, success=False, timestamp=time.time())
    
    def measure_tcp_throughput(self, duration_sec: float = 0.5) -> float:
        """Estimate TCP throughput by sending data for duration"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.safety_scanner_ip, self.safety_scanner_tcp_port))
            
            # Send data as fast as possible for duration
            payload = b'X' * 1024  # 1KB payload
            bytes_sent = 0
            start_time = time.perf_counter()
            
            while (time.perf_counter() - start_time) < duration_sec:
                sent = sock.send(payload)
                bytes_sent += sent
            
            elapsed = time.perf_counter() - start_time
            sock.close()
            
            # Calculate throughput in Mbps
            throughput_mbps = (bytes_sent * 8) / (elapsed * 1_000_000)
            return throughput_mbps
            
        except Exception as e:
            logger.debug(f"TCP throughput measurement failed: {e}")
            return 0.0
    
    def _create_icmp_packet(self, icmp_id: int, icmp_seq: int) -> bytes:
        """Create ICMP Echo Request packet with checksum"""
        # ICMP header: type(8), code(8), checksum(16), id(16), seq(16)
        icmp_type = 8  # Echo Request
        icmp_code = 0
        checksum = 0
        
        # Pack header without checksum
        header = bytearray([icmp_type, icmp_code, 0, 0, (icmp_id >> 8) & 0xFF, icmp_id & 0xFF, 
                           (icmp_seq >> 8) & 0xFF, icmp_seq & 0xFF])
        
        # Calculate checksum
        checksum = self._calculate_checksum(header)
        header[2] = (checksum >> 8) & 0xFF
        header[3] = checksum & 0xFF
        
        return bytes(header)
    
    def _calculate_checksum(self, data: bytearray) -> int:
        """Calculate Internet checksum (RFC 1071)"""
        checksum = 0
        for i in range(0, len(data), 2):
            word = (data[i] << 8) + (data[i+1] if i+1 < len(data) else 0)
            checksum += word
        
        # Add carry and fold to 16 bits
        checksum = (checksum >> 16) + (checksum & 0xFFFF)
        checksum += (checksum >> 16)
        return ~checksum & 0xFFFF
    
    
    def run_probe_cycle(self):
        """Run one complete probe cycle and update metrics - RAW DATA ONLY"""
        # Measure UDP to robot-control
        udp_result = self.measure_udp_rtt(count=10)
        udp_success_gauge.labels(target=self.robot_control_host).set(1 if udp_result.success else 0)
        
        if udp_result.success and udp_result.latency_ms is not None:
            udp_latency_gauge.labels(target=self.robot_control_host).set(udp_result.latency_ms)
            udp_latency_hist.labels(target=self.robot_control_host).observe(udp_result.latency_ms)
            logger.debug(f"UDP RTT (robot-control): {udp_result.latency_ms:.2f}ms")
        
        # Measure TCP to safety-scanner
        tcp_result = self.measure_tcp_handshake()
        tcp_success_gauge.labels(target=self.safety_scanner_host).set(1 if tcp_result.success else 0)
        
        if tcp_result.success and tcp_result.latency_ms is not None:
            tcp_latency_gauge.labels(target=self.safety_scanner_host).set(tcp_result.latency_ms)
            tcp_latency_hist.labels(target=self.safety_scanner_host).observe(tcp_result.latency_ms)
            logger.debug(f"TCP handshake (safety-scanner): {tcp_result.latency_ms:.2f}ms")
        
        # Measure TCP throughput to safety-scanner (every 5th cycle to reduce overhead)
        if not hasattr(self, '_throughput_counter'):
            self._throughput_counter = 0
        self._throughput_counter += 1
        
        if self._throughput_counter >= 5:
            throughput = self.measure_tcp_throughput(duration_sec=0.5)
            tcp_throughput_gauge.labels(target=self.safety_scanner_host).set(throughput)
            logger.debug(f"TCP throughput (safety-scanner): {throughput:.2f} Mbps")
            self._throughput_counter = 0


def main():
    """Main loop: start metrics server and run probes continuously"""
    logger.info("=" * 60)
    logger.info("Network Probe Exporter Starting")
    logger.info("=" * 60)
    logger.info(f"Robot Control: {ROBOT_CONTROL_HOST}:{ROBOT_CONTROL_UDP_PORT} (UDP)")
    logger.info(f"Safety Scanner: {SAFETY_SCANNER_HOST}:{SAFETY_SCANNER_TCP_PORT} (TCP)")
    logger.info(f"Probe Interval: {PROBE_INTERVAL}s")
    logger.info(f"Metrics Port: {METRICS_PORT}")
    logger.info("=" * 60)
    
    # Start Prometheus metrics server
    start_http_server(METRICS_PORT)
    logger.info(f"Metrics server listening on :{METRICS_PORT}/metrics")
    
    # Initialize probe
    probe = NetworkProbe(ROBOT_CONTROL_HOST, ROBOT_CONTROL_UDP_PORT,
                        SAFETY_SCANNER_HOST, SAFETY_SCANNER_TCP_PORT)
    
    # Main loop
    cycle = 0
    try:
        while True:
            cycle += 1
            logger.debug(f"--- Probe Cycle {cycle} ---")
            
            probe.run_probe_cycle()
            
            time.sleep(PROBE_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("\nShutting down probe exporter")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
