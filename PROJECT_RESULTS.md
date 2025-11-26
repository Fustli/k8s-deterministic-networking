# Kubernetes Deterministic Networking with ML-Based QoS Control

## Project Overview

This project implements an intelligent bandwidth management system for Kubernetes clusters running deterministic network workloads. The system uses machine learning principles to monitor critical application latency and automatically throttles best-effort traffic to maintain quality of service guarantees for time-sensitive workloads like robot control and safety systems.

---

## Architecture

### Cluster Infrastructure
- **Platform:** Kubeadm Kubernetes v1.30.14 on Ubuntu 24.04 LTS
- **Nodes:** 3-node cluster (1 control plane, 2 workers)
- **CNI:** Cilium v1.18.3 with eBPF datapath
- **Monitoring:** Prometheus + Grafana stack
- **Network Observability:** Hubble with L7 HTTP metrics

### Key Components

1. **ML Controller (Python)**
   - Monitors application-level latency and jitter using Prometheus metrics
   - Implements IQR (Interquartile Range) jitter calculation
   - Uses EWMA (Exponential Weighted Moving Average) for signal smoothing
   - Dynamically adjusts bandwidth limits via Kubernetes annotations
   - Implements hysteresis control to prevent oscillation

2. **Cilium CNI with Hubble**
   - eBPF-based packet processing for line-rate performance
   - L7 HTTP visibility for latency histograms
   - Network policy enforcement (CiliumNetworkPolicy)
   - Bandwidth manager for egress rate limiting

3. **Application Workloads**
   - **Critical Apps:** robot-control, safety-scanner, robot-factory (priority: critical)
   - **Best-Effort Apps:** telemetry-upload, erp-dashboard, background-traffic (priority: best-effort)
   - Traffic generators for load testing (HTTP, TCP, UDP)

---

## Current System Metrics

### Network Performance (Robot-Factory Critical App)
```
P95 Latency:     8.7 ms    (Target: <10 ms)  ✓
Jitter (IQR):    2.9 ms    (Target: <5 ms)   ✓
Packet Drops:    ~30 p/s   (Legitimate policy enforcement)
Flow Rate:       ~325 f/s  (Healthy eBPF processing)
```

### Bandwidth Management
```
Best-Effort Apps:  1000 Mbps (Unrestricted)
Controller State:  INCREASE mode (metrics are healthy)
Control Action:    Gradual bandwidth increases (+15 Mbps steps)
Cooldown Period:   30 seconds between adjustments
```

### Controller Behavior
The ML controller continuously monitors critical application metrics:
- **When jitter/latency are good:** Gradually increases bandwidth for best-effort apps
- **When jitter spikes:** Aggressively throttles best-effort apps to protect critical traffic
- **When latency high but jitter low:** Gentle throttling (indicates distance, not congestion)

---

## Technical Implementation Details

### 1. Jitter Calculation (IQR Method)
```promql
(histogram_quantile(0.75, sum(rate(hubble_http_request_duration_seconds_bucket{
    destination_workload="robot-factory-deployment"
}[1m])) by (le)) 
- 
histogram_quantile(0.25, sum(rate(hubble_http_request_duration_seconds_bucket{
    destination_workload="robot-factory-deployment"
}[1m])) by (le))) * 1000
```

**Why IQR?** Interquartile Range (Q3 - Q1) measures the spread of latency, which is the true definition of network jitter. This is more accurate than standard deviation for detecting congestion.

### 2. Bandwidth Control Mechanism
The controller modifies the `kubernetes.io/egress-bandwidth` annotation on deployments:
```yaml
spec:
  template:
    metadata:
      annotations:
        kubernetes.io/egress-bandwidth: "115M"  # Dynamically adjusted
```

Cilium's bandwidth manager enforces these limits using eBPF rate limiters at the egress path.

### 3. Network Policies
12 CiliumNetworkPolicies implemented:
- **L7 HTTP visibility** for robot-factory (enables latency metrics)
- **L4 policies** for critical apps (robot-control, safety-scanner)
- **Traffic generator policies** (6 policies for test traffic isolation)
- **Best-effort policies** for throttleable workloads

### 4. Control Loop Logic
```python
if jitter > TARGET_JITTER_MS:
    # Congestion detected
    action = "CONGESTION_THROTTLE"
    bandwidth_change = -AGGRESSIVE_DECREASE_MBPS
elif latency > TARGET_LATENCY_MS and jitter <= TARGET_JITTER_MS:
    # High latency but low jitter (not congestion)
    action = "LATENCY_GENTLE_THROTTLE"
    bandwidth_change = -GENTLE_DECREASE_MBPS
else:
    # Metrics are healthy
    action = "INCREASE"
    bandwidth_change = +INCREASE_STEP_MBPS
```

---

## Key Findings

### 1. L7 Visibility Trade-off
**Initial Approach:** Pure L4 eBPF monitoring (no Envoy proxy)
- **Result:** 52% lower jitter (1.3ms vs 2.7ms)
- **Problem:** No application-level latency metrics for control decisions

**Final Approach:** Selective L7 visibility only on critical apps
- **Result:** 2.9ms jitter with full latency visibility
- **Benefit:** Controller can make intelligent decisions based on actual application performance

**Lesson:** For deterministic systems, L7 metrics are necessary for intelligent control, but should be applied selectively to minimize overhead.

### 2. Node-Specific Performance Characteristics
During testing, we discovered significant node-to-node performance variance:
- **Worker-1:** 14ms jitter at low traffic
- **Worker-2:** 6.5ms jitter at high traffic

**Root cause:** Kernel version difference (6.8.0-87 vs 6.8.0-86) and hardware variations.

**Solution:** Pod placement strategy to colocate traffic generators with target applications on the same node to minimize cross-node latency.

### 3. Packet Drops Are Not Always Bad
Baseline drops: ~30 packets/second
- **Reason:** Legitimate CiliumNetworkPolicy enforcement (default-deny security model)
- **Sources:** System pods without explicit network policies
- **Impact:** Minimal (3.5% of total flows)

**Lesson:** Don't use raw drop rate as the primary control signal. Focus on application-level metrics (latency, jitter) for QoS decisions.

### 4. Controller Stability
The ML controller successfully maintains stability through:
- **EWMA smoothing (α=0.7):** Filters out measurement noise
- **Cooldown periods (30s):** Prevents rapid oscillations
- **Hysteresis control:** Tracks change direction to avoid flip-flopping
- **Minimum bandwidth (10 Mbps):** Prevents complete starvation of best-effort apps

**Observed behavior:** System converges to optimal bandwidth allocation within 2-3 minutes after traffic changes.

---

## Performance Comparison

| Metric | Original (No QoS) | With L4 Controller | With ML Controller |
|--------|-------------------|-------------------|-------------------|
| **Jitter** | 6.5 ms | 1.3 ms (pure eBPF) | 2.9 ms (with L7) |
| **P95 Latency** | ~15 ms | 3.2 ms | 8.7 ms |
| **Packet Drops** | 55 p/s | 28 p/s | 30 p/s |
| **Control Signal** | None | Drop rate | Latency + Jitter |
| **Bandwidth Mgmt** | Static | Drop-based | Application-aware |
| **Determinism** | Poor | Good | Best |

---

## System Validation

### Test Scenarios Executed

1. **Baseline Traffic (Light Load)**
   - HTTP: 20 req/s to robot-factory
   - TCP: 50 Mbps to safety-scanner
   - Result: Controller increases bandwidth to 1000 Mbps

2. **Congestion Injection (Heavy Load)**
   - Background traffic: 500 Mbps
   - Result: Controller throttles to 50 Mbps, jitter remains <5ms

3. **Node Failover**
   - Moved workloads between nodes
   - Result: Controller adapts within 60 seconds

4. **Policy Enforcement**
   - Applied network policies
   - Result: Drops increased but critical apps unaffected

### Validation Metrics
- ✓ Jitter stays below 5ms target under normal load
- ✓ P95 latency under 10ms target
- ✓ Controller responds within 30-60 seconds to congestion
- ✓ No bandwidth oscillations observed
- ✓ Best-effort apps throttled to 10 Mbps minimum (not starved)

---

## Grafana Dashboard

Custom dashboard with 9 panels:
1. **System Protection Status** - Overall health indicator
2. **Packet Drop Rate** - Real-time drop monitoring
3. **Bandwidth Throttling** - Current throttle state
4. **Control Loop Graph** - Shows correlation between drops and bandwidth adjustments
5. **Drop Rate Heatmap** - Distribution across nodes
6. **eBPF Flow Processing** - Cilium health metric
7. **Drop Analysis** - Breakdown by reason
8. **Bandwidth Adjustments** - Controller reaction frequency
9. **Deployment Table** - All bandwidth limits at a glance

---

## Configuration

### ML Controller Environment Variables
```yaml
PROMETHEUS_URL: "http://prometheus.monitoring:9090"
TARGET_JITTER_MS: "5.0"           # Maximum acceptable jitter
TARGET_LATENCY_MS: "10.0"         # Maximum acceptable P95 latency
MIN_BANDWIDTH_MBPS: "10"          # Minimum for best-effort apps
MAX_BANDWIDTH_MBPS: "1000"        # Maximum for best-effort apps
EWMA_ALPHA: "0.7"                 # Smoothing factor
COOLDOWN_PERIOD_SEC: "30"         # Time between adjustments
AGGRESSIVE_DECREASE_MBPS: "50"    # Throttle amount for congestion
INCREASE_STEP_MBPS: "15"          # Gradual increase amount
```

### Cilium Configuration
```yaml
kubeProxyReplacement: true
bandwidthManager: enabled: true
hubble:
  enabled: true
  metrics:
    enabled:
      - dns
      - drop
      - tcp
      - flow
      - port-distribution
      - icmp
      - httpV2:exemplars=true;labelsContext=source_workload,destination_workload
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Kubernetes Cluster                 │
│  ┌────────────────────────────────────────────────┐ │
│  │  Control Plane (kube-master)                   │ │
│  │  - API Server, Scheduler, Controller Manager  │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌──────────────────┐        ┌──────────────────┐  │
│  │  Worker-1        │        │  Worker-2        │  │
│  │  - Cilium Agent  │        │  - Cilium Agent  │  │
│  │  - Hubble        │        │  - Hubble        │  │
│  │  - Critical Apps │        │  - Critical Apps │  │
│  │  - Generators    │        │  - Monitoring    │  │
│  └──────────────────┘        └──────────────────┘  │
└─────────────────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   Prometheus           │
         │   - Scrapes Hubble     │
         │   - Stores metrics     │
         └────────────────────────┘
                      │
            ┌─────────┴─────────┐
            │                   │
            ▼                   ▼
    ┌──────────────┐    ┌──────────────┐
    │ ML Controller│    │   Grafana    │
    │ - Queries    │    │ - Dashboard  │
    │ - Decides    │    │ - Alerts     │
    │ - Updates    │    └──────────────┘
    └──────────────┘
```

---

## Lessons Learned

1. **Metrics Matter More Than Transport**
   - Initial focus on L4 purity was misguided
   - Application-level metrics (L7) are essential for intelligent QoS
   - Trade 1-2ms of overhead for visibility and control

2. **Node Placement is Critical**
   - Pod anti-affinity increased latency by 2x due to cross-node traffic
   - Colocating generators with targets minimizes latency
   - Node-specific performance characteristics must be considered

3. **Control Theory Principles Apply**
   - EWMA smoothing prevents overreaction to noise
   - Cooldown periods prevent oscillation
   - Hysteresis avoids rapid flip-flopping
   - Minimum bandwidth prevents starvation

4. **Security vs Performance**
   - Default-deny network policies cause baseline drops
   - These drops are acceptable (security enforcement)
   - Don't confuse policy drops with congestion drops

5. **eBPF is Production-Ready**
   - Cilium handles 325+ flows/second with minimal overhead
   - Bandwidth manager works reliably
   - L7 visibility adds value when used selectively

---

## Future Work

1. **Multi-Objective Optimization**
   - Currently optimizes for jitter only
   - Could add latency, throughput, and fairness as objectives

2. **Predictive Control**
   - Use historical patterns to preemptively adjust bandwidth
   - Implement time-series forecasting for traffic prediction

3. **Dynamic Threshold Adjustment**
   - Automatically tune TARGET_JITTER_MS based on workload
   - Adaptive cooldown periods based on system stability

4. **Multi-Cluster Support**
   - Extend to multi-cluster environments
   - Coordinate bandwidth management across cluster boundaries

5. **Hardware Acceleration**
   - Investigate XDP for even lower latency
   - Offload to SmartNICs where available

---

## Conclusion

This project demonstrates that intelligent, ML-based bandwidth management can maintain deterministic network performance in Kubernetes environments. By monitoring application-level latency metrics and dynamically throttling best-effort traffic, the system successfully protects critical workloads from congestion while maximizing overall cluster utilization.

**Key Achievement:** Maintained <5ms jitter and <10ms P95 latency for critical applications while allowing best-effort traffic to utilize available bandwidth when conditions permit.

**Production Readiness:** The system is stable, responds predictably to load changes, and requires minimal tuning. The controller has operated for multiple days without oscillation or failures.

---

## Quick Start

```bash
# Deploy monitoring stack
kubectl apply -f k8s/infrastructure/prometheus-deployment.yaml
kubectl apply -f k8s/infrastructure/grafana-deployment.yaml

# Deploy network policies
kubectl apply -f k8s/policies/

# Deploy ML controller
kubectl apply -f k8s/applications/ml_controller_rbac.yaml
kubectl apply -f k8s/applications/ml-controller-configmap.yaml
kubectl apply -f k8s/applications/ml-controller.yaml

# Deploy workloads
kubectl apply -f k8s/applications/

# Access Grafana
kubectl port-forward -n monitoring svc/grafana 3000:3000
# Open http://localhost:3000 (admin/admin123)
```

## Repository Structure
```
k8s-deterministic-networking/
├── controller/
│   ├── ml_controller.py          # Main ML controller
│   └── ml_controller_l4.py       # L4-only version (experimental)
├── k8s/
│   ├── applications/             # App deployments
│   ├── infrastructure/           # Monitoring stack
│   └── policies/                 # Network policies
├── docs/                         # Documentation
└── grafana-dashboard-l4-deterministic.json  # Dashboard
```

---

**Project Status:** ✓ Production-ready  
**Last Updated:** November 24, 2025  
**Maintainer:** K8s Deterministic Networking Team
