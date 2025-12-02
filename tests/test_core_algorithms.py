#!/usr/bin/env python3
"""
Test script for UDP jitter measurement and bandwidth control
Tests the core algorithms without Kubernetes dependencies
"""

import sys
import os

# Add controller directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'controller'))

from network_probe import UDPJitterProbe
from flow_manager import calculate_bandwidth_limit


def test_bandwidth_algorithm():
    """Test the asymmetric AIMD bandwidth control algorithm"""
    print("\n" + "="*60)
    print("Testing Asymmetric AIMD Bandwidth Control Algorithm")
    print("="*60)
    
    # Test Case 1: Healthy state (low jitter, good throughput)
    print("\nTest 1: Healthy State")
    print("  Input: current=500M, jitter=2.0ms, throughput=80Mbps")
    result = calculate_bandwidth_limit(500, 2.0, 80.0)
    print(f"  Output: {result}M (Expected: 510M - slow increase)")
    assert result == 510, f"Expected 510, got {result}"
    
    # Test Case 2: High jitter violation
    print("\nTest 2: High Jitter Violation")
    print("  Input: current=500M, jitter=8.0ms, throughput=80Mbps")
    result = calculate_bandwidth_limit(500, 8.0, 80.0)
    print(f"  Output: {result}M (Expected: 400M - aggressive throttle)")
    assert result == 400, f"Expected 400, got {result}"
    
    # Test Case 3: Low throughput violation
    print("\nTest 3: Low Throughput Violation")
    print("  Input: current=500M, jitter=2.0ms, throughput=30Mbps")
    result = calculate_bandwidth_limit(500, 2.0, 30.0)
    print(f"  Output: {result}M (Expected: 400M - aggressive throttle)")
    assert result == 400, f"Expected 400, got {result}"
    
    # Test Case 4: Lower bound clamping
    print("\nTest 4: Lower Bound Clamping")
    print("  Input: current=50M, jitter=10.0ms, throughput=20Mbps")
    result = calculate_bandwidth_limit(50, 10.0, 20.0)
    print(f"  Output: {result}M (Expected: 10M - clamped to minimum)")
    assert result == 10, f"Expected 10, got {result}"
    
    # Test Case 5: Upper bound clamping
    print("\nTest 5: Upper Bound Clamping")
    print("  Input: current=995M, jitter=1.0ms, throughput=100Mbps")
    result = calculate_bandwidth_limit(995, 1.0, 100.0)
    print(f"  Output: {result}M (Expected: 1000M - clamped to maximum)")
    assert result == 1000, f"Expected 1000, got {result}"
    
    print("\n✅ All bandwidth control algorithm tests passed!")


def test_udp_jitter_probe():
    """Test UDP jitter probe (requires UDP reflector to be running)"""
    print("\n" + "="*60)
    print("Testing UDP Jitter Probe (IQR Method)")
    print("="*60)
    
    # Test with localhost (requires udp_server.py running)
    print("\nNote: This test requires UDP reflector running on localhost:5201")
    print("      Start it with: python controller/udp_server.py")
    
    try:
        probe = UDPJitterProbe('localhost', 5201)
        print("\nSending 50 probe packets...")
        jitter = probe.measure_jitter(count=50)
        print(f"✅ Measured jitter: {jitter:.2f}ms (IQR)")
        
        if jitter > 0:
            print(f"   Jitter calculation successful!")
        else:
            print(f"   Warning: Zero jitter may indicate no responses received")
            
    except Exception as e:
        print(f"⚠️  UDP probe test skipped: {e}")
        print("   Make sure UDP reflector is running: python controller/udp_server.py")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Deterministic Networking Core Algorithm Tests")
    print("="*60)
    
    # Test 1: Bandwidth control algorithm (no dependencies)
    test_bandwidth_algorithm()
    
    # Test 2: UDP jitter probe (requires reflector)
    test_udp_jitter_probe()
    
    print("\n" + "="*60)
    print("Test suite completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
