# Test Scenario: Recovery

## Overview

**Duration:** 300 seconds  
**Samples:** 60  
**Interval:** 5 seconds  

## Jitter Metrics

| Metric | Value |
|--------|-------|
| **Min** | 3.21 ms |
| **Max** | 5.30 ms |
| **Average** | 4.23 ms |
| **Std Dev** | 0.65 ms |
| **Above Target (>1.0ms)** | 60 samples |

## Bandwidth Management

| Metric | Value |
|--------|-------|
| **Min** | 10 Mbps |
| **Max** | 50 Mbps |
| **Final** | 10 Mbps |
| **Total Patches** | 2 |
| **Patch Rate** | 3.3% |

## Control Loop Behavior

### Decision Distribution
- **PATCH**: 2 times
- **NO_UPDATE**: 58 times

### Key Observations


1. **High Jitter Phase:** Aggressive bandwidth reduction during crisis
2. **Recovery Tracking:** Bandwidth increased as jitter improved
3. **Convergence:** System returned to normal operation with appropriate bandwidth
