# ML Controller Test Scenarios

Comprehensive testing framework for the hybrid deterministic-ML network controller.

## 📋 Overview

This directory contains a complete test scenario suite that simulates various network conditions and validates the ML controller's behavior without requiring a live Kubernetes cluster.

## 📁 Directory Structure

```
test_scenarios/
├── scenario_generator.py      # Generates test jitter data
├── visualizer.py              # Creates analysis and reports
├── test_runner.py             # Main orchestration script
├── README.md                  # This file
├── scenarios/                 # Test scenario definitions
├── data/                      # Generated CSV/JSON data
└── results/                   # Generated reports and visualizations
```

## 🎯 Test Scenarios

### 1. **Normal Operation**
- **Description:** Stable operation with low, steady jitter
- **Duration:** 300 seconds (60 measurements @ 5s intervals)
- **Expected Behavior:** Minimal bandwidth adjustments
- **Use Case:** Baseline performance validation

### 2. **Jitter Spike**
- **Description:** Sudden increase in jitter, then recovery
- **Pattern:** Gaussian spike centered at 400s mark
- **Expected Behavior:** Rapid bandwidth reduction, then gradual recovery
- **Use Case:** Transient network issues

### 3. **Sustained High Load**
- **Description:** Prolonged period of high jitter
- **Pattern:** Ramp up → sustain → ramp down
- **Expected Behavior:** Aggressive bandwidth reduction during load
- **Use Case:** High-traffic periods

### 4. **Oscillation**
- **Description:** Jitter oscillates around target threshold
- **Pattern:** Sine wave at 1.0ms ± 0.7ms
- **Expected Behavior:** Frequent bandwidth adjustments
- **Use Case:** Marginal network conditions

### 5. **Degradation**
- **Description:** Gradually increasing jitter over time
- **Pattern:** Linear increase from 0.3ms to ~3.0ms
- **Expected Behavior:** Continuous bandwidth reduction
- **Use Case:** Network performance degradation

### 6. **Recovery**
- **Description:** System recovering from crisis
- **Pattern:** High jitter → gradual recovery to normal
- **Expected Behavior:** Aggressive reduction, then recovery
- **Use Case:** Network crisis and recovery

## 🚀 Quick Start

### Run All Tests
```bash
cd test_scenarios
python3 test_runner.py
```

This will:
1. Generate test scenarios (jitter data)
2. Simulate controller behavior
3. Create visualization reports
4. Generate summary documentation

### View Results
```bash
# Summary overview
cat results/SUMMARY.md

# Specific scenario report
cat results/normal_operation_report.md

# Raw data
cat data/normal_operation.csv
head data/normal_operation.json
```

## 📊 Generated Outputs

### Data Files (in `data/`)
- `*.csv`: Time-series data with jitter, bandwidth, and decisions
- `*.json`: Structured data with metadata

### Reports (in `results/`)
- `SUMMARY.md`: Overview of all scenarios
- `*_report.md`: Detailed analysis per scenario
- `INDEX.md`: Navigation index

### Example CSV Format
```csv
timestamp_sec,jitter_ms,bandwidth_mbps,decision
0,0.30,100,NO_UPDATE
5,0.32,100,NO_UPDATE
10,0.35,100,NO_UPDATE
15,3.50,50,PATCH
20,3.45,50,NO_UPDATE
```

### Example JSON Structure
```json
{
  "scenario": "jitter_spike",
  "duration_seconds": 300,
  "samples": 60,
  "data": [
    {
      "timestamp_sec": 0,
      "jitter_ms": 0.30,
      "bandwidth_mbps": 100,
      "decision": "NO_UPDATE"
    },
    ...
  ]
}
```

## 🔧 Controller Parameters

These parameters are used in all simulations:

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Target Jitter** | 1.0 ms | Threshold for acceptable latency |
| **Min Bandwidth** | 10 Mbps | Minimum allowed bandwidth |
| **Max Bandwidth** | 1000 Mbps | Maximum allowed bandwidth |
| **Decrease Step** | 50 Mbps | Bandwidth reduction when jitter > target |
| **Increase Step** | 10 Mbps | Bandwidth increase when jitter ≤ target |
| **Update Threshold** | 5 Mbps | Minimum change to trigger Kubernetes patch |
| **Control Interval** | 5 seconds | Time between measurements |

## 📈 Analysis Metrics

Each scenario report includes:

- **Jitter Statistics:** Min, max, average, standard deviation
- **Bandwidth Evolution:** Starting, ending, min, max values
- **Control Decisions:** Patch count and frequency
- **Key Observations:** Scenario-specific insights
- **Controller Effectiveness:** Assessment of response appropriateness

## 🔍 Expected Controller Behavior

### Decision Logic
```
if jitter > TARGET_JITTER_MS (1.0ms):
    reduce_bandwidth()  # Decrease by DECREASE_STEP (50Mbps)
else:
    increase_bandwidth()  # Increase by INCREASE_STEP (10Mbps)

if abs(new_bandwidth - current_bandwidth) >= UPDATE_THRESHOLD (5Mbps):
    patch_deployment()  # Apply to Kubernetes
```

### Behavior Patterns

**Normal Operation**
```
Jitter: 0.30-0.35ms (stable, below target)
Bandwidth: 100Mbps → 820Mbps (increases)
Decision: Gradual increase, smooth growth
```

**Jitter Spike**
```
Jitter: 0.30 → 5.0 → 0.30ms (spike and recovery)
Bandwidth: 100 → 10 → 100+Mbps (drops and recovers)
Decision: Rapid decrease, gradual increase
```

## 🧪 Integration with Live Cluster

### Test Against Real Controller

1. **Export Mock Data** to pod environment:
```bash
kubectl create configmap test-scenarios --from-dir=data/
kubectl set env deployment/ml-controller \
  -c controller TEST_MODE=enabled
```

2. **Modify Controller** to use test data:
```python
# In scripts/ml_controller.py
def get_critical_app_latency(self):
    if os.getenv('TEST_MODE'):
        return load_scenario_data()
    return self.metrics.get_critical_app_latency()
```

3. **Run Scenario Replay:**
```bash
kubectl exec -n kube-system ml-controller-* -- \
  python /app/ml_controller.py --replay normal_operation.json
```

## 📝 Example Report Output

```markdown
# Test Scenario: Normal Operation

## Overview
**Duration:** 300 seconds  
**Samples:** 60  

## Jitter Metrics
| Metric | Value |
|--------|-------|
| Min | 0.30 ms |
| Max | 0.35 ms |
| Average | 0.32 ms |
| Above Target | 0 samples |

## Bandwidth Management
| Metric | Value |
|--------|-------|
| Min | 100 Mbps |
| Max | 820 Mbps |
| Total Patches | 72 |
```

## 🛠️ Customization

### Modify Controller Parameters

Edit `scenario_generator.py`:
```python
class ControlLoopSimulator:
    def __init__(self):
        self.target_jitter = 1.5      # Change threshold
        self.decrease_step = 100        # More aggressive decrease
        self.increase_step = 5          # Conservative increase
```

### Add New Scenarios

Add method to `JitterGenerator`:
```python
def generate_custom_scenario(self) -> List[float]:
    """Your custom jitter pattern"""
    jitter = []
    for i in range(self.num_samples):
        value = ...  # Your pattern here
        jitter.append(value)
    return jitter
```

Register in `main()`:
```python
scenarios = {
    ...
    "custom_scenario": generator.generate_custom_scenario,
}
```

## 📊 Analysis Tools

### Python Analysis
```python
import json

with open('data/normal_operation.json') as f:
    data = json.load(f)
    
# Extract metrics
jitter = [d['jitter_ms'] for d in data['data']]
bandwidth = [d['bandwidth_mbps'] for d in data['data']]

# Custom analysis
avg_jitter = sum(jitter) / len(jitter)
jitter_variance = sum((j - avg_jitter)**2 for j in jitter) / len(jitter)
```

### CSV Analysis with Command Line
```bash
# Get statistics
awk -F, '{sum+=$2; if(NR==1) next; print $2}' data/normal_operation.csv | \
  awk '{if(NR==1) min=max=$1; if($1<min) min=$1; if($1>max) max=$1} \
       END{print "Min:", min, "Max:", max}'

# Count patches
grep PATCH data/normal_operation.csv | wc -l
```

## 🎓 Learning Resources

### Understanding the Control Loop
1. Read the scenario generator logic
2. Trace through a single cycle in `ControlLoopSimulator.simulate()`
3. Compare expected vs actual bandwidth changes
4. Review scenario reports for pattern analysis

### Debugging Controller Behavior
1. Check raw CSV data for unexpected decisions
2. Plot jitter and bandwidth together
3. Identify decision boundaries
4. Compare with expected threshold (1.0ms)

## ✅ Validation Checklist

- [ ] All scenarios generate without errors
- [ ] Each scenario has matching CSV and JSON files
- [ ] Reports include key metrics and observations
- [ ] Bandwidth stays within 10-1000 Mbps bounds
- [ ] Patches occur only when change ≥ 5 Mbps
- [ ] Decisions align with jitter measurements
- [ ] No negative or NaN values in data

## 🐛 Troubleshooting

### No data generated
```bash
python3 scenario_generator.py -v  # Verbose mode
```

### Reports missing
```bash
python3 visualizer.py --debug  # Debug output
```

### JSON parse errors
```bash
python3 -m json.tool data/*.json  # Validate JSON
```

## 📚 Further Reading

- [ML Controller Implementation](../scripts/ml_controller.py)
- [Test Results](../TEST_RESULTS.md)
- [Cilium QoS Documentation](https://docs.cilium.io/en/stable/network/ebpf/bandwidth-manager/)
- [Kubernetes Bandwidth Annotations](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/#bandwidth-plugin)

## 📄 License

Part of the k8s-deterministic-networking project.

---

**Version:** 1.0  
**Last Updated:** November 11, 2025  
**Framework:** ML Controller Test Scenarios
