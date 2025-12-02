# k8s-deterministic-networking

ML-based bandwidth controller for Kubernetes protecting critical workloads (robot-control, safety-scanner) from congestion caused by best-effort traffic (telemetry-upload, erp-dashboard).

## Quick Start

```bash
# 1. Deploy critical workloads
kubectl apply -f deployments/critical-apps/

# 2. Deploy best-effort workloads  
kubectl apply -f deployments/best-effort/

# 3. Deploy monitoring (optional)
kubectl apply -f deployments/monitoring/

# 4. Deploy flow manager control plane
kubectl apply -f deployments/base/

# 5. Check status
kubectl logs -n kube-system -l app=flow-manager -f
```

## Architecture

```
Active Probes (TCP+UDP) → Flow Manager → K8s Annotation Patch → Cilium eBPF Enforcement
```

**Key Features:**
- **Active Probing**: Sub-second UDP/TCP measurements bypass Prometheus scrape lag
- **Asymmetric AIMD**: 20% multiplicative decrease (fast throttle), +10M additive increase (slow recovery)
- **Dual Protocol**: UDP jitter for robot-control, TCP latency for safety-scanner
- **IQR Jitter**: Interquartile range calculation robust to outliers

## Project Structure

```
├── src/                    # Python source code
│   ├── controller/         # Flow manager and config loader
│   ├── probes/            # Network probe and UDP reflector
│   └── exporters/         # Bandwidth metrics exporter
├── deployments/           # Kubernetes manifests
│   ├── base/             # Flow manager control plane
│   ├── critical-apps/    # Safety-critical workloads
│   ├── best-effort/      # Throttleable workloads
│   └── monitoring/       # Prometheus + Grafana
├── k8s/                  # Additional Kubernetes resources
│   └── policies/         # Cilium network policies
├── tests/                # Test suite
│   ├── unit/            # Algorithm tests
│   ├── integration/     # Component tests
│   └── system/          # E2E cluster tests
├── scripts/             # Deployment and testing scripts
└── docs/                # Documentation
```

## Configuration

Edit `deployments/base/critical-apps-config.yaml`:

```yaml
critical_apps:
  - name: robot-control
    protocol: UDP
    max_jitter_ms: 1.0    # Jitter threshold
    priority: 100          # Highest priority
    
  - name: safety-scanner
    protocol: TCP
    max_jitter_ms: 2.0
    priority: 90

control:
  min_bandwidth: 10       # Mbps
  max_bandwidth: 1000     # Mbps
```

## Testing

```bash
# Unit tests (no dependencies)
python3 tests/unit/test_asymmetric_aimd.py

# Integration tests (requires venv)
source venv/bin/activate
python tests/integration/test_dual_metrics.py

# All tests
pytest tests/ -v
```

## Requirements

- Kubernetes 1.28+
- Cilium CNI v1.18+ with `bandwidthManager.enabled=true`
- Python 3.11+
- `kubernetes`, `requests`, `prometheus_client` packages

## Documentation

- [Deployment Guide](docs/setup/DEPLOYMENT_GUIDE.md)
- [Dashboard Guide](docs/DASHBOARD_GUIDE.md)
- [Bandwidth Control Verification](docs/reports/BANDWIDTH_CONTROL_VERIFICATION.md)
- [Project Results](PROJECT_RESULTS.md)

## License

See [LICENSE](LICENSE)