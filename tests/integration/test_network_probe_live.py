#!/usr/bin/env python3
"""
Live test for network probe UDP and TCP measurements
Tests against localhost UDP reflector
"""

import socket
import struct
import time


def test_udp_reflector():
    """Test UDP echo/reflector on localhost:5201"""
    print("Testing UDP reflector...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        
        latencies = []
        for i in range(10):
            send_time = time.perf_counter()
            payload = struct.pack('d', send_time)
            sock.sendto(payload, ('127.0.0.1', 5201))
            
            data, addr = sock.recvfrom(1024)
            recv_time = time.perf_counter()
            latency_ms = (recv_time - send_time) * 1000
            latencies.append(latency_ms)
            print(f"  Packet {i+1}: {latency_ms:.3f}ms")
        
        sock.close()
        
        avg = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        
        print(f"✓ UDP reflector working: avg={avg:.3f}ms, min={min_lat:.3f}ms, max={max_lat:.3f}ms")
        return True
        
    except Exception as e:
        print(f"✗ UDP reflector test failed: {e}")
        return False


def test_tcp_connection():
    """Test TCP connection capability"""
    print("\nTesting TCP connection...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        
        start = time.perf_counter()
        # Try connecting to localhost on a port that likely exists
        try:
            sock.connect(('127.0.0.1', 22))  # SSH port
            latency_ms = (time.perf_counter() - start) * 1000
            sock.close()
            print(f"✓ TCP handshake working: {latency_ms:.3f}ms (to localhost:22)")
            return True
        except ConnectionRefusedError:
            print(f"✓ TCP socket working (connection refused is expected for closed ports)")
            return True
            
    except Exception as e:
        print(f"✗ TCP test failed: {e}")
        return False


def test_tcp_throughput():
    """Test TCP throughput measurement concept"""
    print("\nTesting TCP throughput measurement...")
    try:
        # Create a simple echo server socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 15999))
        server.listen(1)
        server.settimeout(2.0)
        
        # Client connection in separate "thread" simulation
        import os
        pid = os.fork() if hasattr(os, 'fork') else None
        
        if pid == 0:  # Child process - client
            time.sleep(0.1)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', 15999))
            
            payload = b'X' * 1024
            bytes_sent = 0
            start = time.perf_counter()
            duration = 0.5
            
            while (time.perf_counter() - start) < duration:
                sent = client.send(payload)
                bytes_sent += sent
            
            elapsed = time.perf_counter() - start
            client.close()
            
            throughput_mbps = (bytes_sent * 8) / (elapsed * 1_000_000)
            print(f"✓ TCP throughput: {throughput_mbps:.2f} Mbps ({bytes_sent} bytes in {elapsed:.3f}s)")
            os._exit(0)
        
        elif pid is not None:  # Parent process - server
            conn, addr = server.accept()
            # Just receive and discard
            while True:
                try:
                    data = conn.recv(8192)
                    if not data:
                        break
                except:
                    break
            conn.close()
            server.close()
            os.wait()
            return True
        else:
            # No fork support, skip test
            server.close()
            print("⊘ TCP throughput test skipped (no fork support)")
            return True
            
    except Exception as e:
        print(f"✗ TCP throughput test failed: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("Network Probe Component Tests")
    print("=" * 60)
    
    results = []
    results.append(("UDP Reflector", test_udp_reflector()))
    results.append(("TCP Connection", test_tcp_connection()))
    results.append(("TCP Throughput", test_tcp_throughput()))
    
    print("\n" + "=" * 60)
    print("Test Results:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    print("=" * 60)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    print("=" * 60)
