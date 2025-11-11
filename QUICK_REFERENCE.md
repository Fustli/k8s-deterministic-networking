# Quick Reference: ML Controller Operations

## Essential Commands

### Monitor Controller
```bash
# Watch logs in real-time
kubectl logs -n kube-system deployment/ml-controller -f

# Check current bandwidth
kubectl get deploy telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'

# View patch history
kubectl describe deployment telemetry-upload-deployment | grep "Annotations:"
```

### Run Tests
```bash
# Generate test scenarios and reports
cd test_scenarios
python3 test_runner.py

# View summary
cat results/SUMMARY.md

# Display ASCII visualizations
python3 visual_summary.py
```

### Deploy/Update
```bash
# Deploy all manifests
kubectl apply -f manifests/ml_controller_rbac.yaml
kubectl apply -f manifests/ml-controller-configmap.yaml
kubectl apply -f manifests/ml-controller.yaml
kubectl apply -f manifests/robot-control-policy.yaml
kubectl apply -f manifests/safety-scanner-policy.yaml
kubectl apply -f manifests/best-effort-policy.yaml

# Verify deployment
kubectl get all -n kube-system | grep ml-controller
```

## Control Loop Parameters

**File:** `scripts/ml_controller.py`

```python
ControlParameters:
  TARGET_JITTER_MS = 1.0              # Bandwidth increases if jitter < this
  MIN_BANDWIDTH_MBPS = 10             # Absolute minimum allocation
  MAX_BANDWIDTH_MBPS = 1000           # Absolute maximum allocation
  DECREASE_STEP_MBPS = 50             # How much to reduce when congested
  INCREASE_STEP_MBPS = 10             # How much to increase when free
```

**Decision Logic:**
- **IF** jitter > 1.0ms → Reduce bandwidth by 50Mbps
- **IF** jitter < 1.0ms → Increase bandwidth by 10Mbps
- **Constraint:** 10Mbps ≤ bandwidth ≤ 1000Mbps

## Test Scenario Quick Start

**Generate data without running full pipeline:**
```bash
cd test_scenarios
python3 -c "from scenario_generator import *; gen = JitterGenerator(); [print(f'{s}: {len(gen.generate(s))} samples') for s in ['normal_operation', 'jitter_spike', 'sustained_high_load', 'oscillation', 'degradation', 'recovery']]"
```

**View specific scenario report:**
```bash
cat test_scenarios/results/normal_operation.md
cat test_scenarios/results/jitter_spike.md
cat test_scenarios/results/sustained_high_load.md
```

## Troubleshooting Matrix

| Issue | Check | Fix |
|-------|-------|-----|
| Pod CrashLoopBackOff | `kubectl logs -n kube-system ml-controller` | Reapply ml_controller_rbac.yaml |
| Bandwidth not updating | `kubectl get deployment telemetry-upload-deployment -o yaml` | Check RBAC permissions |
| Jitter always 0.50ms | Prometheus not responding | Deploy Prometheus stack or wait for fallback |
| Policies not enforcing | `kubectl get cnp --all-namespaces` | Verify status: VALID |

## Cluster Health Check

```bash
# All-in-one health verification
echo "=== Nodes ===" && \
kubectl get nodes -o wide && \
echo -e "\n=== ML Controller ===" && \
kubectl get deployment -n kube-system ml-controller && \
echo -e "\n=== Cilium Policies ===" && \
kubectl get cnp && \
echo -e "\n=== Test Results ===" && \
ls -lh test_scenarios/results/
```

## File Locations Quick Map

| Component | Location | Status |
|-----------|----------|--------|
| ML Controller Code | `scripts/ml_controller.py` | ✅ Running |
| Deployment YAML | `manifests/ml-controller.yaml` | ✅ Deployed |
| RBAC | `manifests/ml_controller_rbac.yaml` | ✅ Active |
| Network Policies | `manifests/*-policy.yaml` | ✅ Valid |
| Test Framework | `test_scenarios/` | ✅ Complete |
| Results | `test_scenarios/results/` | ✅ Generated |
| Data | `test_scenarios/data/` | ✅ Available |

## Emergency Commands

```bash
# Pause controller (scale to 0 replicas)
kubectl scale deployment ml-controller -n kube-system --replicas=0

# Resume controller
kubectl scale deployment ml-controller -n kube-system --replicas=1

# Force bandwidth reset to baseline
kubectl patch deployment telemetry-upload-deployment -p '{"spec":{"template":{"metadata":{"annotations":{"kubernetes.io/egress-bandwidth":"100M"}}}}}'

# View all patches applied today
kubectl describe deployment telemetry-upload-deployment | grep -A 1 "Annotations:"

# Full controller restart
kubectl rollout restart deployment -n kube-system ml-controller
```

## Production Checklist

- [ ] Prometheus metrics returning real jitter values
- [ ] Liveness/readiness probes added to deployment
- [ ] Hysteresis implemented (deadband ±0.2ms)
- [ ] EMA smoothing enabled (alpha=0.3)
- [ ] Rate limiting active (min 10s between patches)
- [ ] 2+ replicas deployed for HA
- [ ] Container image pushed to registry
- [ ] 48-hour load test completed
- [ ] Alerting configured for anomalies
- [ ] Documentation updated for team

## Performance Targets

| Metric | Target | Current Status |
|--------|--------|---|
| Jitter (critical apps) | <1.5ms 95th %ile | ✅ On target in tests |
| Bandwidth (best-effort) | 10-1000Mbps dynamic | ✅ Adjusting correctly |
| Decision latency | <5s per control loop | ✅ 5s intervals verified |
| Controller overhead | <1Mbps | ✅ Estimated <1Mbps |
| Pod restart time | <5s | ✅ Typical 3s measured |

## Useful kubectl Aliases

```bash
# Add to ~/.bashrc
alias kgml='kubectl get deployment -n kube-system ml-controller'
alias klog='kubectl logs -n kube-system deployment/ml-controller -f'
alias klast20='kubectl logs -n kube-system deployment/ml-controller --tail=20'
alias kbw='kubectl get deploy telemetry-upload-deployment -o jsonpath="{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}"'
alias kpol='kubectl get cnp --all-namespaces'
```

---

**Keep this file handy for daily operations!**

Last Updated: November 11, 2025
