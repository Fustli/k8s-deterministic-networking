# Copilot Instructions for k8s-deterministic-networking

## Project Overview

ML-based bandwidth controller for Kubernetes protecting critical workloads (robot-control, safety-scanner) from congestion caused by best-effort traffic (telemetry-upload, erp-dashboard). Uses **active TCP/UDP probing** for real-time jitter measurement and throttles via Kubernetes deployment annotations enforced by Cilium's eBPF bandwidth manager.

## Cluster Environment

- **Platform**: 3-node kubeadm cluster (1 master, 2 workers) on university servers
- **CNI**: Cilium v1.18+ with `bandwidthManager.enabled=true`, `kubeProxyReplacement=true`
- **Monitoring**: Prometheus + Grafana; Hubble for L7 HTTP metrics (visualization only)
- **Why active probing**: Hubble provides L7 metrics but we need L4 latency/jitter with sub-second reaction times - active probing bypasses Prometheus scrape lag

## Architecture

```
Active Probes (TCP+UDP) → Flow Manager → K8s Annotation Patch → Cilium eBPF Enforcement
```

**Key insight**: Bandwidth control uses `kubernetes.io/egress-bandwidth` annotation patching (not CiliumNetworkPolicy) because Cilium v1.18 doesn't support direct policy bandwidth fields.

## Critical Code Patterns

### Controller Logic (controller/flow_manager.py) ← CANONICAL LOCATION
- **Jitter calculation**: Uses IQR (Q3-Q1) from probe history, not standard deviation
- **Asymmetric control**: Fast throttle down (`STEP_DOWN=100`), slow release up (`STEP_UP=10`)
- **Dual protocol probing**: Measures both TCP handshake and UDP send latency; uses `max()` for conservative control
- **Kubernetes patching**: Patches deployment spec.template.metadata.annotations to trigger Cilium enforcement

```python
# Control decision pattern - DO NOT simplify the asymmetry
if jitter > TARGET_JITTER_MS:
    new_bw = max(MIN_BW, current_bw - STEP_DOWN)  # Aggressive decrease
elif jitter < (TARGET_JITTER_MS * 0.5):
    new_bw = min(MAX_BW, current_bw + STEP_UP)    # Gentle increase
```

### Application Priority Labels
```yaml
labels:
  priority: critical    # Protected (robot-control, safety-scanner)
  priority: best-effort # Throttleable (telemetry-upload, erp-dashboard)
```

### Network Policy Pattern (manifests/policies/)
- Use `CiliumNetworkPolicy` (not standard NetworkPolicy)
- L7 visibility policies enable Hubble HTTP metrics for dashboards (not control loop)

## File Organization

| Directory | Purpose |
|-----------|---------|
| `controller/` | Python flow manager (canonical location) |
| `manifests/applications/` | Workload deployments with priority labels |
| `manifests/infrastructure/` | Prometheus, Grafana monitoring stack |
| `manifests/policies/` | CiliumNetworkPolicy definitions |
| `scripts/` | Test and deployment automation |
| `tests/` | Pytest tests (note: some have stale imports referencing `scripts/`) |

## Testing Commands

```bash
# Run unit tests
pytest tests/ -v --cov=controller

# HTTP-based traffic test (baseline → noise → validation phases)
./scripts/test-flow-manager-http.sh

# Watch controller behavior
kubectl logs -n kube-system -l app=flow-manager -f

# Check current bandwidth annotation
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations}'
```

## Key Dependencies

- **kubernetes** Python client (v28+): Use `client.AppsV1Api().patch_namespaced_deployment()` for annotations
- **Cilium v1.18+**: Requires `bandwidthManager.enabled=true` in Helm values

## Common Pitfalls

1. **Don't use Prometheus/Hubble for real-time control** - L7 only + scrape lag; use active L4 probing
2. **Annotation format**: Must be `"100M"` (string with M suffix), not numeric
3. **Controller namespace**: Runs in `kube-system`, watches `default` namespace deployments
4. **Probe failures**: Handle gracefully with fallback jitter values, don't crash the control loop
5. **Test imports**: Some tests have stale imports from `scripts/flow_manager.py` - canonical location is `controller/flow_manager.py`

## Configuration

Environment variables (set in `manifests/control/flow-manager.yaml`):
- `TARGET_HOST`: Service DNS to probe (default: `robot-control-svc.default.svc.cluster.local`)
- `TARGET_JITTER_MS`: Threshold triggering throttle (default: `3.0`)
- `MIN_BW/MAX_BW`: Bandwidth limits in Mbps (default: `10`/`1000`)
- `PROBE_INTERVAL`: Seconds between probes (default: `0.5`)

## Grafana Dashboard

Import `grafana-dashboard-ml-qos.json` for visualization (not control feedback):
- Critical app latency (P50/P95/P99) from Hubble L7 metrics
- Best-effort bandwidth allocations
- Controller throttle/release events

Access: `kubectl port-forward -n monitoring svc/grafana 3000:3000` → http://localhost:3000 (admin/admin123)
