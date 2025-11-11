# Test Scenario: Degradation

## Overview

**Duration:** 300 seconds  
**Samples:** 60  
**Interval:** 5 seconds  

## Jitter Metrics

| Metric | Value |
|--------|-------|
| **Min** | 0.30 ms |
| **Max** | 0.85 ms |
| **Average** | 0.60 ms |
| **Std Dev** | 0.12 ms |
| **Above Target (>1.0ms)** | 0 samples |

## Bandwidth Management

| Metric | Value |
|--------|-------|
| **Min** | 110 Mbps |
| **Max** | 700 Mbps |
| **Final** | 700 Mbps |
| **Total Patches** | 60 |
| **Patch Rate** | 100.0% |

## Control Loop Behavior

### Decision Distribution
- **PATCH**: 60 times
- **NO_UPDATE**: 0 times

### Key Observations


1. **Gradual Degradation:** Steady increase in jitter over time
2. **Responsive Adjustments:** Controller made continuous bandwidth reductions
3. **Load Trend:** Indicates sustained increase in network utilization
