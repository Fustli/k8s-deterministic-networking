# Test Scenario: Sustained High Load

## Overview

**Duration:** 300 seconds  
**Samples:** 60  
**Interval:** 5 seconds  

## Jitter Metrics

| Metric | Value |
|--------|-------|
| **Min** | 0.30 ms |
| **Max** | 5.70 ms |
| **Average** | 3.86 ms |
| **Std Dev** | 1.68 ms |
| **Above Target (>1.0ms)** | 55 samples |

## Bandwidth Management

| Metric | Value |
|--------|-------|
| **Min** | 10 Mbps |
| **Max** | 150 Mbps |
| **Final** | 10 Mbps |
| **Total Patches** | 8 |
| **Patch Rate** | 13.3% |

## Control Loop Behavior

### Decision Distribution
- **PATCH**: 8 times
- **NO_UPDATE**: 52 times

### Key Observations


1. **Sustained High Load:** Bandwidth continuously reduced during load period
2. **Aggressive Response:** Multiple patches to reach minimum acceptable bandwidth
3. **Recovery Phase:** Gradual bandwidth increase as load decreased
