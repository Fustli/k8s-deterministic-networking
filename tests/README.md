# Test Suite

Comprehensive tests for the deterministic networking control system.

## Test Organization

### unit/
Standalone algorithm tests (no dependencies):
- `test_asymmetric_aimd.py` - Asymmetric AIMD 20% multiplicative decrease
- `test_bandwidth_algorithm.py` - Legacy bandwidth algorithm tests
- `test_flow_manager_logic.py` - Control decision logic

Run: `python3 tests/unit/test_asymmetric_aimd.py`

### integration/
Component integration tests (require dependencies):
- `test_network_probe_live.py` - UDP reflector and TCP measurement
- `test_network_probe_integration.py` - NetworkProbe class methods
- `test_dual_metrics.py` - UDP/TCP dual protocol capability

Run: `source venv/bin/activate && python tests/integration/test_dual_metrics.py`

### system/
End-to-end cluster tests (require Kubernetes):
- Place system-level tests here (e.g., full deployment verification)

Run: `kubectl apply -f ... && pytest tests/system/`

## Quick Test

```bash
# Unit tests (fast, no dependencies)
python3 tests/unit/test_asymmetric_aimd.py

# Integration tests (requires venv)
source venv/bin/activate
python tests/integration/test_dual_metrics.py

# All tests
pytest tests/ -v --cov=src
```

## Test Results

All current tests passing:
- ✓ 10/10 asymmetric AIMD algorithm tests
- ✓ 3/3 network probe component tests  
- ✓ 6/6 bandwidth enforcement tests
- ✓ Dual protocol (UDP/TCP) capability verified
