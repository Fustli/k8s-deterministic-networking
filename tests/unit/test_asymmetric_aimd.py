#!/usr/bin/env python3
"""
Test for Asymmetric AIMD bandwidth control algorithm with 20% multiplicative decrease

Tests the formula:
- Violation: Limit_new = Limit_old - (Limit_old × 0.20)  [Multiplicative Decrease]
- Stable: Limit_new = Limit_old + 10  [Additive Increase]
"""

def asymmetric_aimd(current_bw, jitter_ms, max_jitter_ms, min_bw=10, max_bw=1000):
    """
    Asymmetric AIMD: Cut deep when unsafe, recover slowly when safe
    
    Args:
        current_bw: Current bandwidth in Mbps
        jitter_ms: Measured jitter in milliseconds
        max_jitter_ms: Jitter threshold triggering throttle
        min_bw: Minimum bandwidth limit (Mbps)
        max_bw: Maximum bandwidth limit (Mbps)
    
    Returns:
        new_bw: Adjusted bandwidth in Mbps
    """
    
    # Violation: Multiplicative Decrease (20%)
    if jitter_ms > max_jitter_ms:
        reduction = int(current_bw * 0.20)
        new_bw = current_bw - reduction
        new_bw = max(min_bw, new_bw)  # Clamp to minimum
        return new_bw
    
    # Stable (jitter < 50% of threshold): Additive Increase (+10 Mbps)
    elif jitter_ms < (max_jitter_ms * 0.5):
        new_bw = current_bw + 10
        new_bw = min(max_bw, new_bw)  # Clamp to maximum
        return new_bw
    
    # Within range: Maintain
    else:
        return current_bw


def test_healthy_state():
    """Test additive increase when jitter is low (< 50% threshold)"""
    result = asymmetric_aimd(current_bw=500, jitter_ms=2.0, max_jitter_ms=5.0)
    assert result == 510, f"Expected 510, got {result}"
    print("✓ Test 1: Healthy state (jitter 2.0ms < 2.5ms threshold) -> +10 Mbps")


def test_high_jitter_violation():
    """Test multiplicative decrease (20%) when jitter exceeds threshold"""
    result = asymmetric_aimd(current_bw=500, jitter_ms=6.0, max_jitter_ms=5.0)
    # 500 - (500 × 0.20) = 500 - 100 = 400
    assert result == 400, f"Expected 400, got {result}"
    print("✓ Test 2: High jitter violation (6.0ms > 5.0ms) -> -20% = -100 Mbps")


def test_percentage_decrease_scales():
    """Test that 20% decrease scales with bandwidth"""
    # At 200 Mbps: 20% = 40 Mbps reduction
    result = asymmetric_aimd(current_bw=200, jitter_ms=6.0, max_jitter_ms=5.0)
    assert result == 160, f"Expected 160, got {result} (200 - 20% = 160)"
    print("✓ Test 3: 20% scales correctly (200M -> 160M)")
    
    # At 1000 Mbps: 20% = 200 Mbps reduction
    result = asymmetric_aimd(current_bw=1000, jitter_ms=6.0, max_jitter_ms=5.0)
    assert result == 800, f"Expected 800, got {result} (1000 - 20% = 800)"
    print("✓ Test 4: 20% scales correctly (1000M -> 800M)")


def test_lower_bound_clamping():
    """Test that bandwidth never goes below minimum"""
    result = asymmetric_aimd(current_bw=50, jitter_ms=6.0, max_jitter_ms=5.0)
    # 50 - (50 × 0.20) = 50 - 10 = 40, which is above min of 10
    assert result == 40, f"Expected 40, got {result}"
    print("✓ Test 5: Above minimum (50M -> 40M)")
    
    # Very low bandwidth: should clamp to minimum
    result = asymmetric_aimd(current_bw=12, jitter_ms=6.0, max_jitter_ms=5.0)
    # 12 - (12 × 0.20) = 12 - 2.4 ≈ 10 (rounded), clamped to 10 min
    assert result == 10, f"Expected 10, got {result}"
    print("✓ Test 6: Clamped to minimum (12M -> 10M minimum)")


def test_upper_bound_clamping():
    """Test that bandwidth never exceeds maximum"""
    result = asymmetric_aimd(current_bw=995, jitter_ms=2.0, max_jitter_ms=5.0)
    # 995 + 10 = 1005, should clamp to 1000 max
    assert result == 1000, f"Expected 1000, got {result}"
    print("✓ Test 7: Clamped to maximum (995M -> 1000M maximum)")


def test_at_maximum():
    """Test behavior when already at maximum bandwidth"""
    result = asymmetric_aimd(current_bw=1000, jitter_ms=2.0, max_jitter_ms=5.0)
    assert result == 1000, f"Expected 1000, got {result}"
    print("✓ Test 8: At maximum stays at maximum (1000M -> 1000M)")


def test_at_minimum_recovery():
    """Test that minimum bandwidth can still recover"""
    result = asymmetric_aimd(current_bw=10, jitter_ms=2.0, max_jitter_ms=5.0)
    assert result == 20, f"Expected 20, got {result}"
    print("✓ Test 9: Minimum can recover (10M -> 20M)")


def test_midrange_maintain():
    """Test that midrange jitter maintains bandwidth"""
    # Jitter between 50% threshold and max should maintain
    result = asymmetric_aimd(current_bw=500, jitter_ms=3.0, max_jitter_ms=5.0)
    # 3.0ms is between 2.5ms (50%) and 5.0ms (100%), should maintain
    assert result == 500, f"Expected 500, got {result}"
    print("✓ Test 10: Midrange jitter maintains (3.0ms → 500M unchanged)")


if __name__ == '__main__':
    print("=" * 60)
    print("Asymmetric AIMD Algorithm Tests")
    print("Formula: Violation → -20% | Stable → +10M")
    print("=" * 60)
    
    test_healthy_state()
    test_high_jitter_violation()
    test_percentage_decrease_scales()
    test_lower_bound_clamping()
    test_upper_bound_clamping()
    test_at_maximum()
    test_at_minimum_recovery()
    test_midrange_maintain()
    
    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
