import sys
import os
from pathlib import Path

# Add project root to sys.path so tests can import the controller module
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ml_controller import BandwidthController


def test_adjust_bandwidth_decrease():
    c = BandwidthController()
    c.current_bandwidth = 200
    # Simulate high jitter
    new_bw = c.adjust_bandwidth(current_jitter=10.0)
    assert new_bw < 200


def test_adjust_bandwidth_increase():
    c = BandwidthController()
    c.current_bandwidth = 100
    # Low jitter -> should increase
    new_bw = c.adjust_bandwidth(current_jitter=0.1)
    assert new_bw > 100
