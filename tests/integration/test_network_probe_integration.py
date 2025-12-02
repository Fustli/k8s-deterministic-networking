#!/usr/bin/env python3
"""
Integration test for network_probe.py
Tests the actual NetworkProbe class methods
"""

import sys
sys.path.insert(0, '/home/ubuntu/k8s-deterministic-networking/controller')

from network_probe import NetworkProbe
import time

def test_network_probe():
    """Test NetworkProbe class with localhost targets"""
    print("=" * 60)
    print("NetworkProbe Integration Test")
    print("=" * 60)
    
    # Initialize probe with localhost targets
    # UDP reflector on 5201, SSH on 22 for TCP
    probe = NetworkProbe(
        robot_control_host='127.0.0.1',
        robot_control_udp_port=5201,
        safety_scanner_host='127.0.0.1', 
        safety_scanner_tcp_port=22
    )
    
    print("\n1. Testing UDP RTT measurement...")
    udp_result = probe.measure_udp_rtt(count=10)
    if udp_result.success:
        print(f"   ✓ UDP RTT: {udp_result.latency_ms:.3f}ms")
    else:
        print(f"   ✗ UDP RTT failed")
    
    print("\n2. Testing TCP handshake measurement...")
    tcp_result = probe.measure_tcp_handshake()
    if tcp_result.success:
        print(f"   ✓ TCP handshake: {tcp_result.latency_ms:.3f}ms")
    else:
        print(f"   ✗ TCP handshake failed")
    
    print("\n3. Testing TCP throughput measurement...")
    throughput = probe.measure_tcp_throughput(duration_sec=0.3)
    if throughput > 0:
        print(f"   ✓ TCP throughput: {throughput:.2f} Mbps")
    else:
        print(f"   ⊘ TCP throughput: N/A (connection may be refused)")
    
    print("\n" + "=" * 60)
    print("Integration test complete!")
    print("=" * 60)
    
    # Check critical results
    if udp_result.success and tcp_result.success:
        print("✓ Core functionality working")
        return True
    else:
        print("✗ Some measurements failed")
        return False

if __name__ == '__main__':
    success = test_network_probe()
    sys.exit(0 if success else 1)
