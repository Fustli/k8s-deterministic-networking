# Test Scenario: Oscillation

## Overview

**Duration:** 300 seconds  
**Samples:** 60  
**Interval:** 5 seconds  

## Jitter Metrics

| Metric | Value |
|--------|-------|
| **Min** | 1.00 ms |
| **Max** | 1.70 ms |
| **Average** | 1.46 ms |
| **Std Dev** | 0.20 ms |
| **Above Target (>1.0ms)** | 59 samples |

## Bandwidth Management

| Metric | Value |
|--------|-------|
| **Min** | 10 Mbps |
| **Max** | 110 Mbps |
| **Final** | 10 Mbps |
| **Total Patches** | 3 |
| **Patch Rate** | 5.0% |

## Control Loop Behavior

### Decision Distribution
- **PATCH**: 3 times
- **NO_UPDATE**: 57 times

### Key Observations


1. **Threshold Oscillation:** Jitter hovering around target threshold
2. **Control Instability:** Frequent bandwidth adjustments due to oscillation
3. **Hysteresis Needed:** Consider adding hysteresis to reduce oscillation
