#!/usr/bin/env python3
"""
Standalone test for bandwidth control algorithm
No external dependencies required
"""


def calculate_bandwidth_limit(current_limit_mbps: int, jitter_ms: float, throughput_mbps: float) -> int:
    """
    Asymmetric AIMD (Additive Increase Multiplicative Decrease) Control Algorithm
    
    Args:
        current_limit_mbps: Current bandwidth limit in Mbps
        jitter_ms: Measured UDP jitter in milliseconds
        throughput_mbps: Measured TCP throughput in Mbps
    
    Returns:
        New bandwidth limit in Mbps (clamped between 10-1000 Mbps)
    """
    # SLA thresholds
    MAX_JITTER = 5.0  # milliseconds
    MIN_THROUGHPUT = 50.0  # Mbps
    
    # Bandwidth range
    MIN_BW = 10  # Mbps
    MAX_BW = 1000  # Mbps
    
    # Control step sizes (asymmetric)
    THROTTLE_STEP = 100  # Mbps - aggressive decrease
    RECOVERY_STEP = 10   # Mbps - conservative increase
    
    # Check for SLA violations
    jitter_violation = jitter_ms > MAX_JITTER
    throughput_violation = throughput_mbps < MIN_THROUGHPUT
    
    if jitter_violation or throughput_violation:
        # CONGESTION: Aggressive throttling
        new_limit = current_limit_mbps - THROTTLE_STEP
    else:
        # HEALTHY: Slow recovery
        new_limit = current_limit_mbps + RECOVERY_STEP
    
    # Clamp to valid range
    new_limit = max(MIN_BW, min(MAX_BW, new_limit))
    
    return new_limit


def main():
    """Test the bandwidth control algorithm"""
    print("\n" + "="*70)
    print("Asymmetric AIMD Bandwidth Control Algorithm - Test Suite")
    print("="*70)
    
    tests = [
        {
            "name": "Healthy State (Low Jitter + Good Throughput)",
            "current": 500,
            "jitter": 2.0,
            "throughput": 80.0,
            "expected": 510,
            "reason": "Slow increase (+10M)"
        },
        {
            "name": "High Jitter Violation",
            "current": 500,
            "jitter": 8.0,
            "throughput": 80.0,
            "expected": 400,
            "reason": "Aggressive throttle (-100M)"
        },
        {
            "name": "Low Throughput Violation",
            "current": 500,
            "jitter": 2.0,
            "throughput": 30.0,
            "expected": 400,
            "reason": "Aggressive throttle (-100M)"
        },
        {
            "name": "Both Violations (Severe Congestion)",
            "current": 500,
            "jitter": 10.0,
            "throughput": 20.0,
            "expected": 400,
            "reason": "Aggressive throttle (-100M)"
        },
        {
            "name": "Lower Bound Clamping",
            "current": 50,
            "jitter": 10.0,
            "throughput": 20.0,
            "expected": 10,
            "reason": "Clamped to minimum (10M)"
        },
        {
            "name": "Upper Bound Clamping",
            "current": 995,
            "jitter": 1.0,
            "throughput": 100.0,
            "expected": 1000,
            "reason": "Clamped to maximum (1000M)"
        },
        {
            "name": "At Maximum (Already Clamped)",
            "current": 1000,
            "jitter": 2.0,
            "throughput": 80.0,
            "expected": 1000,
            "reason": "Already at max, stays at 1000M"
        },
        {
            "name": "At Minimum (Already Clamped)",
            "current": 10,
            "jitter": 2.0,
            "throughput": 80.0,
            "expected": 20,
            "reason": "Healthy, increase to 20M"
        },
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(tests, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"  Input:    current={test['current']}M, jitter={test['jitter']}ms, throughput={test['throughput']}Mbps")
        
        result = calculate_bandwidth_limit(test['current'], test['jitter'], test['throughput'])
        
        print(f"  Expected: {test['expected']}M ({test['reason']})")
        print(f"  Result:   {result}M", end="")
        
        if result == test['expected']:
            print(" ✅ PASS")
            passed += 1
        else:
            print(f" ❌ FAIL (got {result}, expected {test['expected']})")
            failed += 1
    
    print("\n" + "="*70)
    print(f"Test Results: {passed} passed, {failed} failed out of {len(tests)} total")
    print("="*70)
    
    if failed == 0:
        print("\n✅ All tests passed! Algorithm working correctly.\n")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the algorithm.\n")
        return 1


if __name__ == "__main__":
    exit(main())
