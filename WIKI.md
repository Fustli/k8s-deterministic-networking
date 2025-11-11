# K8s Deterministic Networking - Complete Wiki

Welcome to the **K8s Deterministic Networking** project wiki! This page provides a comprehensive guide to understanding, deploying, and extending this ML-driven QoS controller.

---

## Table of Contents

1. [What Is This Project?](#what-is-this-project)
2. [Problem Statement](#problem-statement)
3. [Solution Architecture](#solution-architecture)
4. [How It Works](#how-it-works)
5. [Getting Started](#getting-started)
6. [Deployment Guide](#deployment-guide)
7. [Testing & Validation](#testing--validation)
8. [Monitoring & Debugging](#monitoring--debugging)
9. [Customization](#customization)
10. [Troubleshooting](#troubleshooting)
11. [FAQ](#faq)

---

## What Is This Project?

**K8s Deterministic Networking** is a production-ready implementation of **ML-driven QoS (Quality of Service) management** for Kubernetes clusters using Cilium CNI.

### Key Innovation

This project combines:
- **Cilium eBPF** for kernel-level priority queuing (sub-microsecond latency)
- **Machine learning feedback control** to dynamically manage best-effort traffic
- **Prometheus metrics** integration for real-time jitter monitoring

**Result**: Critical applications get guaranteed low-latency service while best-effort traffic maximizes available bandwidth.

### Use Cases

- **Autonomous Vehicles**: Safety-critical traffic prioritized over telemetry
- **Surgical Robotics**: Surgery coordination guaranteed <1.5ms latency
- **Industrial IoT**: Real-time control over data collection
- **Financial Trading**: Low-latency order execution alongside risk monitoring

---

## Problem Statement

### The Challenge

In modern cloud-native environments, two types of applications compete for network resources:

1. **Critical Applications** (robot control, safety systems)
   - Need: Guaranteed latency < 1.5ms
   - Flexibility: Low (jitter causes mission-critical failures)
   - Example: Surgical robot must respond within milliseconds

2. **Best-Effort Applications** (telemetry, dashboards, analytics)
   - Need: Maximize throughput when possible
   - Flexibility: High (can tolerate degradation)
   - Example: Dashboard can handle slower updates during congestion

### Traditional Approaches

```
Approach 1: Static Allocation
├─ Critical: Reserve 500Mbps
├─ Best-effort: Reserve 500Mbps
└─ Problem: Wastes bandwidth if critical traffic is low

Approach 2: No QoS
├─ Both compete equally
└─ Problem: Critical traffic can't meet latency SLA

Approach 3: Manual Tuning
├─ Operator adjusts limits based on load
└─ Problem: Reactive, doesn't adapt automatically
```

### Our Solution: Dynamic Feedback Control

```
Real-time Measurement
    ↓
    Compare to Target (1.0ms jitter)
    ↓
    Decision Logic (proportional control)
    ↓
    Adjust bandwidth automatically
    ↓
    Loop every 5 seconds
```

---

## Solution Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────┐
│      Kubernetes Cluster (3 nodes, Kubeadm)         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Cilium CNI v1.18.3 (eBPF BandwidthManager)        │
│  ┌─────────────────────────────────────────┐       │
│  │ Priority Queue 1: UDP:5201 (robot)      │       │
│  │ Priority Queue 2: TCP:5202 (safety)     │       │
│  │ Priority Queue 3: TCP:80 (telemetry)    │       │
│  └─────────────────────────────────────────┘       │
│           ↑ (managed by eBPF, kernel)              │
│           │                                         │
│  ┌─────────────────────────────────────────┐       │
│  │  ML Controller (kube-system)            │       │
│  │  ├─ Query jitter: Prometheus            │       │
│  │  ├─ Calculate: Control logic            │       │
│  │  ├─ Action: Patch deployment            │       │
│  │  └─ Interval: Every 5 seconds           │       │
│  └─────────────────────────────────────────┘       │
│           ↑ (queries metrics)                      │
│           │                                         │
│  ┌─────────────────────────────────────────┐       │
│  │  Prometheus + Hubble                    │       │
│  │  Metric: hubble_flow_latency_seconds    │       │
│  │  Returns: 95th percentile jitter        │       │
│  └─────────────────────────────────────────┘       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Why This Choice |
|-----------|-----------|-----------------|
| Orchestration | Kubernetes 1.30 (Kubeadm) | Standard cloud-native |
| CNI | Cilium 1.18.3 | eBPF kernel-level performance |
| Container Runtime | containerd 1.7.28 | Lightweight, OCI-compliant |
| ML Controller | Python 3.11 | Fast development, proven libraries |
| Metrics | Prometheus + Hubble | Cloud-native standard |
| QoS Mechanism | Kubernetes annotations | Native, no custom CRDs |

---

## How It Works

### Control Loop Walkthrough

#### Scenario: Network Load Increases

```
Time T=0s: Normal operation
├─ Critical traffic: 50Mbps, 0.5ms jitter ✓
├─ Telemetry: 100Mbps
└─ Network utilization: 30%

Time T=5s: ML Controller iteration 1
├─ Query: jitter = 0.5ms
├─ Target: 1.0ms
├─ Decision: 0.5 < 1.0 → INCREASE
├─ Action: telemetry bandwidth 100Mbps → 110Mbps
└─ Pod restarted, new rate limit applied

... (repeats every 5 seconds)

Time T=40s: Network saturated (operator starts heavy download)
├─ Telemetry now sending at 600Mbps
├─ All network capacity consumed
└─ Critical traffic delayed in kernel buffer

Time T=45s: ML Controller detects problem
├─ Query: jitter = 3.2ms (above 1.0ms target!)
├─ Decision: 3.2 > 1.0 → DECREASE
├─ Action: telemetry bandwidth 600Mbps → 550Mbps
└─ Kernel throttles telemetry, frees up capacity

Time T=50s: Jitter recovers
├─ Query: jitter = 1.1ms
├─ Decision: 1.1 > 1.0 → DECREASE to 500Mbps
└─ Continue protecting critical traffic

Time T=100s: System stabilized
├─ Jitter: 0.95-1.05ms (perfect!)
├─ Telemetry: 400-480Mbps (good for best-effort)
└─ Critical apps: Happy, latency < 1.5ms ✓
```

### Decision Logic

```python
def adjust_bandwidth(current_jitter_ms, target_jitter_ms=1.0):
    """
    Proportional control with asymmetric steps
    """
    if current_jitter_ms > target_jitter_ms:
        # Congestion detected! Protect critical apps fast
        new_bandwidth = current_bandwidth - 50Mbps  # Aggressive
    elif current_jitter_ms < target_jitter_ms:
        # Network available! Increase best-effort bandwidth slow
        new_bandwidth = current_bandwidth + 10Mbps  # Conservative
    else:
        # Perfect! No change
        new_bandwidth = current_bandwidth
    
    # Apply safety constraints
    return max(10Mbps, min(new_bandwidth, 1000Mbps))
```

### Why Asymmetric Steps?

| Situation | Action | Size | Reason |
|-----------|--------|------|--------|
| Congestion | Decrease | -50Mbps | **FAST**: Protect critical apps immediately |
| Available | Increase | +10Mbps | **SLOW**: Gradually grow, prevent waste |

This prevents wild oscillations while prioritizing safety for critical apps.

### Kubernetes Annotations in Action

```yaml
# Before: Low bandwidth (conservative)
spec.template.metadata.annotations:
  kubernetes.io/egress-bandwidth: "100M"

# After: Higher bandwidth (more available)
spec.template.metadata.annotations:
  kubernetes.io/egress-bandwidth: "110M"

# Kubelet sees change → Pod restart
# containerd restarts container
# Kernel re-applies qdisc rate limit
# New bandwidth takes effect!
```

---

## Getting Started

### Prerequisites

```bash
# Kubernetes 1.30+
kubectl version --short

# containerd runtime
kubectl get nodes -o wide

# Cilium CNI (check for BandwidthManager)
kubectl get daemonset -n kube-system cilium

# Prometheus/Hubble (optional, has graceful fallback)
kubectl get pods -n cilium hubble-ui
```

### Quick Deploy (5 minutes)

```bash
# 1. Apply RBAC (security configuration)
kubectl apply -f manifests/ml_controller_rbac.yaml

# 2. Apply ConfigMap (controller configuration)
kubectl apply -f manifests/ml-controller-configmap.yaml

# 3. Deploy ML Controller
kubectl apply -f manifests/ml-controller.yaml

# 4. Verify deployment
kubectl get deployment -n kube-system ml-controller
kubectl logs -n kube-system deployment/ml-controller -f

# Output should show:
# INFO: Connecting to Kubernetes API...
# INFO: Control loop starting (5s interval)
# INFO: Current jitter: 0.50ms
# INFO: Bandwidth unchanged: 100M
```

---

## Deployment Guide

### Step 1: Deploy Network Policies

Network policies define which applications get which priority.

```bash
# Deploy policies for critical applications
kubectl apply -f manifests/robot-control-policy.yaml
kubectl apply -f manifests/safety-scanner-policy.yaml
kubectl apply -f manifests/best-effort-policy.yaml

# Verify policies
kubectl get ciliumnetworkpolicies
kubectl describe cnp robot-control-policy

# Output should show: VALID (all endpoints match)
```

**What each policy does:**

| Policy | Traffic | Priority | Purpose |
|--------|---------|----------|---------|
| robot-control-policy | UDP:5201 | HIGH | Guaranteed latency <1.5ms |
| safety-scanner-policy | TCP:5202 | MEDIUM | Guaranteed latency <2.0ms |
| best-effort-policy | TCP:80 | LOW | Dynamically managed |

### Step 2: Deploy ML Controller

```bash
# Create RBAC (allows controller to patch deployments)
kubectl apply -f manifests/ml_controller_rbac.yaml

# Create ConfigMap (controller code)
kubectl apply -f manifests/ml-controller-configmap.yaml

# Deploy the controller pod
kubectl apply -f manifests/ml-controller.yaml

# Check logs (should show control loop running)
kubectl logs -n kube-system deployment/ml-controller -f
```

### Step 3: Deploy Sample Applications

```bash
# Deploy robot control (high priority)
kubectl apply -f manifests/robot-control-pod.yaml

# Deploy telemetry app (best-effort, bandwidth managed)
kubectl apply -f manifests/robot-factory-application.yaml

# Verify deployment
kubectl get pods
kubectl get deployment telemetry-upload-deployment

# Check current bandwidth
kubectl get deployment telemetry-upload-deployment -o jsonpath=\
'{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'
# Output: 100M
```

### Step 4: Monitor in Action

```bash
# Watch bandwidth change in real-time
watch -n 5 'kubectl get deployment \
telemetry-upload-deployment -o jsonpath=\
"{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}"'

# Output updates every 5 seconds:
# 100M ← Initial
# 110M ← Increased
# 120M ← Keep going!
# ... (continues until jitter detected)
```

---

## Testing & Validation

### Run Test Scenarios

The project includes 6 realistic network condition scenarios:

```bash
cd test_scenarios
python3 test_runner.py

# Output:
# ✓ Generating scenarios...
# ✓ Running simulations...
# ✓ Creating reports...
# ✓ Generating visualizations...
# 
# Results in: test_scenarios/results/
```

### Test Scenarios

| Scenario | Pattern | What It Tests |
|----------|---------|---------------|
| **Normal Operation** | Stable low jitter (0.30-0.38ms) | Optimal bandwidth growth |
| **Jitter Spike** | Sudden congestion (0.50→3.00ms) | Fast reaction to overload |
| **Sustained High Load** | Progressive degradation | Long-term stability |
| **Oscillation** | Jitter at threshold | Hysteresis need detection |
| **Degradation** | Step-wise increase | Threshold sensitivity |
| **Recovery** | Gradual restoration | Graceful recovery |

### Analyze Results

```bash
# View summary
cat test_scenarios/results/SUMMARY.md

# Sample output:
# Normal Operation:
#   Min Jitter: 0.30ms
#   Max Jitter: 0.38ms
#   Avg Jitter: 0.35ms
#   Min Bandwidth: 100Mbps
#   Max Bandwidth: 700Mbps
#   Decision: Aggressively increased from initial 100Mbps
```

### Validate on Live Cluster

```bash
# 1. Generate load (in separate terminal)
kubectl exec -it pod/robot-factory-pod -- \
  iperf3 -c telemetry-upload-pod -t 60 -b 500M

# 2. Monitor controller decisions
kubectl logs -n kube-system deployment/ml-controller -f --timestamps

# 3. Watch bandwidth changes
watch -n 1 'kubectl get deployment \
telemetry-upload-deployment -o jsonpath=\
"{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth} \
[jitter: $(kubectl exec prometheus-pod -- \
promtool query instant \"hubble_flow_latency_seconds\" 2>/dev/null | \
grep value || echo \"fallback\")\}"'
```

---

## Monitoring & Debugging

### Check Controller Status

```bash
# Deployment status
kubectl get deployment -n kube-system ml-controller
kubectl describe deployment -n kube-system ml-controller

# Pod logs
kubectl logs -n kube-system deployment/ml-controller
kubectl logs -n kube-system deployment/ml-controller --previous  # Crashed?

# Events (check for errors)
kubectl get events -n kube-system --sort-by='.lastTimestamp'
```

### View Jitter Metrics

```bash
# Query Prometheus directly
kubectl port-forward -n cilium svc/prometheus 9090:9090

# Then in browser: http://localhost:9090
# Query: histogram_quantile(0.95, 
#        rate(hubble_flow_latency_seconds_bucket[60s]))
```

### Debug Network Policies

```bash
# View all policies
kubectl get ciliumnetworkpolicies

# Check specific policy
kubectl describe cnp robot-control-policy

# Validate policy syntax
kubectl apply -f manifests/robot-control-policy.yaml --dry-run=client

# Check which pods matched
kubectl get pods --show-labels
```

### Check Bandwidth Limits

```bash
# Current bandwidth on deployment
kubectl get deployment telemetry-upload-deployment -o yaml | \
grep -A5 annotations

# Track bandwidth history
kubectl get deployment telemetry-upload-deployment -o jsonpath=\
'{.spec.template.metadata.annotations}' | jq

# Check pod-level limits
kubectl exec pod/telemetry-upload-xxx -- \
tc qdisc show dev eth0  # Shows kernel qdisc rules
```

---

## Customization

### Change Target Jitter

Edit `manifests/ml-controller-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ml-controller-config
data:
  controller.py: |
    TARGET_JITTER_MS = 0.5  # More aggressive (lower latency)
    # or
    TARGET_JITTER_MS = 2.0  # More lenient (more bandwidth)
```

Then redeploy:
```bash
kubectl apply -f manifests/ml-controller-configmap.yaml
kubectl rollout restart deployment/ml-controller -n kube-system
```

### Change Bandwidth Steps

Modify control loop behavior:

```python
# Current: Asymmetric (fast decrease, slow increase)
DECREASE_STEP_MBPS = 50    # Aggressive when congested
INCREASE_STEP_MBPS = 10    # Conservative when available

# Alternative 1: More aggressive growth
DECREASE_STEP_MBPS = 50
INCREASE_STEP_MBPS = 30    # Faster bandwidth allocation

# Alternative 2: Fine-grained control
DECREASE_STEP_MBPS = 25    # Smoother decrease
INCREASE_STEP_MBPS = 5     # Very conservative
```

### Change Bandwidth Range

Control the minimum and maximum per-deployment:

```python
MIN_BANDWIDTH_MBPS = 10      # Never starve best-effort
MAX_BANDWIDTH_MBPS = 1000    # Safety ceiling

# For more constrained environments:
MIN_BANDWIDTH_MBPS = 50      # Minimum 50Mbps
MAX_BANDWIDTH_MBPS = 500     # Maximum 500Mbps
```

### Add More Applications

```bash
# 1. Create network policy
kubectl apply -f - << EOF
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: my-app-policy
spec:
  endpointSelector:
    matchLabels:
      app: my-app
  ingress:
  - toPorts:
    - ports:
      - port: "8080"
        protocol: TCP
EOF

# 2. Deploy application
kubectl apply -f manifests/my-app-deployment.yaml

# 3. Add to ML Controller
# Update CONTROLLER_TARGETS in configmap to manage my-app
```

---

## Troubleshooting

### Issue: Controller Pod Not Starting

```bash
# Check pod status
kubectl get pod -n kube-system -l app=ml-controller

# View logs
kubectl logs -n kube-system deployment/ml-controller

# Common causes:
# - RBAC permissions: Check ClusterRole
# - ConfigMap missing: kubectl get cm ml-controller-config
# - Image pull failed: Check image availability
```

### Issue: Prometheus Metrics Unavailable

```bash
# Expected: Graceful fallback to 0.50ms
# Check logs:
kubectl logs -n kube-system deployment/ml-controller | grep -i prometheus

# Configure Prometheus:
# 1. Deploy Prometheus and Hubble
# 2. Verify metrics exist:
kubectl exec prometheus-pod -- \
promtool query instant "hubble_flow_latency_seconds_bucket"
```

### Issue: Bandwidth Not Changing

```bash
# Check if controller is running
kubectl get deployment -n kube-system ml-controller

# View control loop decisions
kubectl logs -n kube-system deployment/ml-controller -f

# Common causes:
# - No deployment named "telemetry-upload-deployment"
# - RBAC permissions insufficient
# - Pod annotations not writable
```

### Issue: High Jitter Despite Controller

```bash
# 1. Verify Cilium policies are active
kubectl get ciliumnetworkpolicies

# 2. Check network policies status
kubectl describe cnp robot-control-policy

# 3. Verify bandwidth limits are applied
kubectl exec pod/telemetry-xxx -- tc class show dev eth0

# 4. Check for network saturation
kubectl top nodes    # Node CPU/memory
kubectl top pods     # Pod resource usage

# Solution: Increase network capacity or reduce load
```

---

## FAQ

**Q: Why asymmetric bandwidth steps (-50Mbps vs +10Mbps)?**

A: When congested, we need to **protect critical apps FAST**. When available, we can **safely grow bandwidth SLOW** to avoid waste. This prevents oscillation while maintaining safety.

**Q: How is jitter measured?**

A: We query Prometheus for the **95th percentile** of latency from Cilium's Hubble metrics over 60 seconds. The 95th percentile better represents real-world user experience than average.

**Q: What happens if Prometheus is down?**

A: The controller uses a **graceful fallback to 0.50ms**, assuming low jitter. It keeps running (no crash), just slightly sub-optimally until Prometheus recovers.

**Q: Can I run multiple controllers?**

A: Currently: single instance (SPOF). Roadmap: Deploy 2+ replicas with leader election to eliminate single point of failure.

**Q: How is this different from vanilla Kubernetes QoS?**

A: Kubernetes QoS classes are static (Guaranteed, Burstable, BestEffort). This project adds **dynamic feedback control** that adapts in real-time to network conditions.

**Q: Can I use Flannel instead of Cilium?**

A: Flannel doesn't support eBPF priority queuing. You'd lose the guaranteed latency feature. Cilium is required for this project.

**Q: How much overhead does the controller add?**

A: Very low! ML controller runs once per 5 seconds, uses ~50MB memory, <100m CPU. The eBPF qdisc is kernel-level with microsecond overhead.

**Q: Can I deploy this on EKS/GKE/AKS?**

A: Yes! Any managed Kubernetes with:
- Cilium CNI support
- BandwidthManager enabled
- Prometheus/Hubble metrics (optional)

**Q: What's the deployment risk?**

A: Low! The controller only patches one deployment (telemetry-upload). Network policies are read-only. Revert by removing controller: `kubectl delete deployment -n kube-system ml-controller`

---

## Next Steps

1. **Deploy**: Follow [Deployment Guide](#deployment-guide)
2. **Test**: Run [Test Scenarios](#testing--validation)
3. **Monitor**: Set up [Monitoring](#monitoring--debugging)
4. **Customize**: Adjust [parameters](#customization)
5. **Extend**: Add more applications or policies

---

**Need help?** Open an issue on GitHub!

**Last Updated**: November 2025
