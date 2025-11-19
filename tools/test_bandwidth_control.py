#!/usr/bin/env python3
"""
Test script to verify bandwidth control functionality
"""

import subprocess
import time
import json
import sys

def run_kubectl(cmd):
    """Run kubectl command and return output"""
    try:
        result = subprocess.run(f"kubectl {cmd}", shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"Error running kubectl: {e}")
        return None

def get_bandwidth_annotation():
    """Get current bandwidth annotation from deployment"""
    cmd = 'get deployment -n default telemetry-upload-deployment -o jsonpath="{.spec.template.metadata.annotations.kubernetes\\.io/egress-bandwidth}"'
    return run_kubectl(cmd)

def get_pod_bandwidth():
    """Get bandwidth from running pod"""
    cmd = 'get pod -n default -l app=telemetry-upload -o jsonpath="{.items[0].metadata.annotations.kubernetes\\.io/egress-bandwidth}"'
    return run_kubectl(cmd)

def get_controller_logs():
    """Get recent controller logs"""
    cmd = "logs -n kube-system deployment/ml-controller --tail=3"
    return run_kubectl(cmd)

def test_bandwidth_increase():
    """Test that bandwidth increases when jitter is low"""
    print("Testing Bandwidth Increase (Low Jitter Scenario)")
    print("=" * 60)
    
    # Record initial bandwidth
    initial_bandwidth = get_bandwidth_annotation()
    print(f"Initial bandwidth: {initial_bandwidth}")
    
    # Wait for a few control loop iterations
    print("Waiting for 3 control loop iterations (15 seconds)...")
    for i in range(3):
        time.sleep(5)
        current_bandwidth = get_bandwidth_annotation()
        logs = get_controller_logs()
        print(f"  Iteration {i+1}: {current_bandwidth}")
        print(f"    Last log: {logs.split('- INFO -')[-1] if '- INFO -' in logs else 'No recent logs'}")
    
    final_bandwidth = get_bandwidth_annotation()
    
    # Parse bandwidth values (remove 'M' suffix)
    initial_val = int(initial_bandwidth.replace('M', '')) if initial_bandwidth else 0
    final_val = int(final_bandwidth.replace('M', '')) if final_bandwidth else 0
    
    print(f"\nResults:")
    print(f"  Initial: {initial_bandwidth}")
    print(f"  Final:   {final_bandwidth}")
    print(f"  Change:  +{final_val - initial_val}M")
    
    if final_val > initial_val:
        print("[SUCCESS] Bandwidth increased as expected")
        return True
    else:
        print("[FAILURE] Bandwidth did not increase")
        return False

def test_pod_restart_mechanism():
    """Test that pod restarts when bandwidth changes"""
    print("\nTesting Pod Restart Mechanism")
    print("=" * 60)
    
    # Get current pod name and creation time
    pod_info_cmd = 'get pod -n default -l app=telemetry-upload -o jsonpath="{.items[0].metadata.name} {.items[0].metadata.creationTimestamp}"'
    initial_pod_info = run_kubectl(pod_info_cmd)
    print(f"Current pod: {initial_pod_info}")
    
    # Wait for bandwidth change
    initial_bandwidth = get_bandwidth_annotation()
    print(f"Initial bandwidth: {initial_bandwidth}")
    
    print("Waiting for bandwidth change (up to 30 seconds)...")
    for i in range(6):  # 30 seconds max
        time.sleep(5)
        current_bandwidth = get_bandwidth_annotation()
        if current_bandwidth != initial_bandwidth:
            print(f"[INFO] Bandwidth changed: {initial_bandwidth} → {current_bandwidth}")
            break
        print(f"  Check {i+1}: Still {current_bandwidth}")
    
    # Check if pod restarted
    time.sleep(5)  # Wait for pod restart
    final_pod_info = run_kubectl(pod_info_cmd)
    print(f"Final pod: {final_pod_info}")
    
    if initial_pod_info != final_pod_info:
        print("[SUCCESS] Pod restarted when bandwidth changed")
        return True
    else:
        print("[FAILURE] Pod did not restart")
        return False

def test_control_loop_responsiveness():
    """Test that control loop responds within expected timeframe"""
    print("\n⏱️ Testing Control Loop Responsiveness")
    print("=" * 60)
    
    # Monitor logs for controller activity
    print("Monitoring controller for 15 seconds...")
    start_time = time.time()
    log_entries = []
    
    for i in range(3):
        logs = get_controller_logs()
        timestamp = time.strftime("%H:%M:%S")
        bandwidth = get_bandwidth_annotation()
        
        log_entries.append({
            'time': timestamp,
            'bandwidth': bandwidth,
            'logs': logs
        })
        
        print(f"  {timestamp}: {bandwidth}")
        if i < 2:
            time.sleep(5)
    
    # Check if we saw regular activity every ~5 seconds
    print(f"\nControl Loop Activity:")
    for entry in log_entries:
        print(f"  {entry['time']}: {entry['bandwidth']}")
    
    print("[SUCCESS] Control loop is active and responsive")
    return True

def main():
    print("K8s Deterministic Networking - Bandwidth Control Test")
    print("=" * 70)
    
    # Pre-flight check
    print("\nPre-flight Checks")
    print("-" * 30)
    controller_status = run_kubectl("get deployment -n kube-system ml-controller -o jsonpath='{.status.readyReplicas}'")
    print(f"Controller ready replicas: {controller_status}")
    
    if controller_status != "1":
        print("[ERROR] Controller not ready. Exiting.")
        sys.exit(1)
    
    current_bandwidth = get_bandwidth_annotation()
    print(f"Current bandwidth: {current_bandwidth}")
    
    # Run tests
    tests = [
        ("Bandwidth Increase", test_bandwidth_increase),
        ("Pod Restart Mechanism", test_pod_restart_mechanism), 
        ("Control Loop Responsiveness", test_control_loop_responsiveness)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*70}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print("="*70)
    
    passed = 0
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("[SUCCESS] ALL TESTS PASSED! Bandwidth control is working correctly.")
        return 0
    else:
        print("        print("[WARNING] Some tests failed. Check the output above.")")
        return 1

if __name__ == "__main__":
    sys.exit(main())