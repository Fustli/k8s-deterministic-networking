# Kubernetes Deterministic Networking

A production-ready ML-based controller system for implementing deterministic networking in Kubernetes clusters using Cilium CNI.

## Overview

This project provides an intelligent bandwidth management system that dynamically adjusts network bandwidth for best-effort applications while ensuring QoS guarantees for critical workloads. The ML controller monitors real-time network jitter through Prometheus/Hubble and automatically adjusts bandwidth allocations using Kubernetes annotations.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ML Controller │◄──►│   Prometheus    │◄──►│     Hubble      │
│                 │    │   Monitoring    │    │   Network Obs.  │
└─────────┬───────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Kubernetes API │◄──►│     Cilium      │◄──►│  Network Flows  │
│  Bandwidth Ctrl │    │   CNI/eBPF      │    │   QoS Control   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Project Structure

```
├── cluster-setup/           # Cluster configuration and status
├── config/                  # ML controller configuration
│   └── .env                 # Controller environment variables
├── infrastructure/          # Infrastructure as Code
│   └── cilium/              # Cilium CNI configurations
├── k8s/                     # Kubernetes manifests
│   ├── applications/        # Application deployments with priority labels
│   │   ├── ml-controller.yaml
│   │   ├── ml-controller-rbac.yaml
│   │   ├── ml-controller-configmap.yaml
│   │   ├── workload-applications.yaml
│   │   └── http-traffic-generator.yaml
│   ├── infrastructure/      # Monitoring stack
│   │   ├── prometheus-deployment.yaml
│   │   └── grafana-deployment.yaml
│   └── policies/            # Cilium network policies with L7 visibility
│       ├── robot-control-policy.yaml
│       ├── safety-scanner-policy.yaml
│       ├── best-effort-policy.yaml
│       └── robot-factory-l7-policy.yaml
├── scripts/                 # Test and deployment scripts
│   ├── test-ml-controller-http.sh
│   └── test-traffic-iperf.sh
├── src/                     # Source code
│   ├── ml_controller.py     # Production ML controller
│   └── setup-monitoring.sh  # Monitoring stack setup
├── tests/                   # Test suite
│   ├── e2e/                 # End-to-end tests
│   ├── integration/         # Integration tests
│   ├── unit/                # Unit tests
│   └── test_ml_controller.py
└── docs/                    # Documentation
    ├── guides/              # Setup and learning guides
    └── setup/               # Deployment documentation
```

## Quick Start

### Prerequisites
- Kubernetes 1.28+ cluster with 3 nodes
- Cilium 1.18+ CNI with Hubble metrics enabled
- Prometheus for metrics collection
- kubectl and helm installed

### Deploy the System
```bash
# 1. Deploy monitoring infrastructure
kubectl apply -f k8s/infrastructure/prometheus-deployment.yaml
kubectl apply -f k8s/infrastructure/grafana-deployment.yaml

# 2. Apply network policies with L7 visibility
kubectl apply -f k8s/policies/

# 3. Deploy ML controller
kubectl apply -f k8s/applications/ml-controller-rbac.yaml
kubectl apply -f k8s/applications/ml-controller-configmap.yaml
kubectl apply -f k8s/applications/ml-controller.yaml

# 4. Deploy workload applications
kubectl apply -f k8s/applications/workload-applications.yaml
kubectl apply -f k8s/applications/http-traffic-generator.yaml
```

### Verify Deployment
```bash
# Check controller status and auto-discovery
kubectl logs -n default -l app=ml-controller -f

# Monitor bandwidth adjustments (best-effort apps)
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'
kubectl get deployment erp-dashboard-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'

# Access Grafana dashboards
kubectl port-forward -n monitoring svc/grafana 3000:3000
# Open http://localhost:3000 (admin/admin123)
# Navigate to: Dashboards > Applications > "Application QoS: Critical vs Best-Effort"
```

## Configuration

The ML controller uses auto-discovery based on pod labels and environment configuration:

### Application Priority Labels
Applications are automatically discovered based on their pod template labels:
```yaml
# Critical applications (protected, never throttled)
labels:
  priority: "critical"
# Examples: robot-factory, robot-control, safety-scanner

# Best-effort applications (dynamically throttled)
labels:
  priority: "best-effort"
# Examples: telemetry-upload, erp-dashboard
```

### Controller Configuration (`config/.env`)
```bash
# Prometheus/Monitoring
PROMETHEUS_URL=http://prometheus.monitoring:9090
TARGET_APPLICATION=robot-factory-deployment  # Critical app to monitor

# QoS Thresholds
TARGET_JITTER_MS=2.0      # Maximum acceptable jitter for critical apps
TARGET_LATENCY_MS=10.0    # Maximum acceptable latency for critical apps

# Bandwidth Control Limits
MIN_BANDWIDTH_MBPS=10     # Minimum bandwidth for best-effort apps
MAX_BANDWIDTH_MBPS=1000   # Maximum bandwidth for best-effort apps

# Control Parameters
EWMA_ALPHA=0.7            # Smoothing factor for metrics
COOLDOWN_PERIOD_SEC=30    # Minimum time between adjustments
```

### Deployment
```bash
# Controller runs in default namespace, monitors all namespaces
kubectl apply -f k8s/applications/ml-controller.yaml

# Check auto-discovered applications
kubectl logs -n default -l app=ml-controller | grep "Discovered deployments"
```

## Monitoring

### Grafana Dashboard
Access the dashboard at `http://localhost:3000` (after port-forward):
- **Dashboard**: "Application QoS: Critical vs Best-Effort" in Applications folder
- **Credentials**: admin/admin123
- **Refresh Rate**: 5 seconds
- **Metrics**: Smoothed latency, jitter, bandwidth with 2-minute averaging

### Key Panels
1. **Critical App Latency** (P50/P95/P99): HTTP request duration for robot-factory
2. **Critical App Jitter**: IQR-based jitter calculation showing network stability
3. **Best-Effort Bandwidth**: Current egress bandwidth limits (check controller logs for real-time values)
4. **Request Rates**: HTTP requests/sec for all applications
5. **Correlation Panels**: Latency vs Bandwidth relationships

### Prometheus Queries
```promql
# Critical app P95 latency (smoothed)
histogram_quantile(0.95, avg_over_time(
  rate(hubble_http_request_duration_seconds_bucket{destination_workload="robot-factory-deployment"}[2m])[2m:30s]
))

# Best-effort app request rate
sum(rate(hubble_http_requests_total{destination_workload=~"telemetry-upload-deployment|erp-dashboard-deployment"}[2m]))

# Flow processing rate (Hubble health)
rate(hubble_flows_processed_total{status="received"}[2m])
```

### Controller Logs
```bash
# View bandwidth adjustments in real-time
kubectl logs -n default -l app=ml-controller -f | grep "bandwidth"

# Example output:
# Updated best-effort bandwidth: telemetry-upload-deployment → 15Mbps
# Updated best-effort bandwidth: erp-dashboard-deployment → 15Mbps
```

## Testing

### Run Test Suite
```bash
cd /home/ubuntu/k8s-deterministic-networking
pytest tests/ -v --cov=src
```

### Manual Traffic Tests
```bash
# HTTP-based traffic test with baseline/noise/validation phases
./scripts/test-ml-controller-http.sh

# Legacy iperf3 traffic test
./scripts/test-traffic-iperf.sh
```

### Verify Controller Behavior
```bash
# 1. Monitor critical app latency
kubectl exec -n default deployment/http-traffic-generator -- \
  curl -w "@curl-format.txt" -s http://robot-factory-service.default.svc.cluster.local/api/status

# 2. Watch bandwidth adjustments
watch "kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations}' | jq"

# 3. Generate high network load
kubectl run stress --image=networkstatic/iperf3 --restart=Never -- \
  iperf3 -c robot-factory-service.default.svc.cluster.local -t 120 -P 10
```

## How It Works

### Auto-Discovery
The ML controller automatically discovers applications at startup:
1. Scans all deployments across all namespaces
2. Reads `priority` label from pod template specs
3. Identifies `critical` apps to monitor (protected workloads)
4. Identifies `best-effort` apps to throttle (adjustable bandwidth)

### Control Loop
```
1. Query Prometheus for critical app metrics (HTTP latency histograms)
2. Calculate jitter using IQR (Interquartile Range) method
3. Apply EWMA smoothing to reduce noise
4. Compare against TARGET_JITTER_MS threshold
5. If jitter too high:
   → Reduce bandwidth for all best-effort apps
6. If jitter acceptable:
   → Gradually increase bandwidth for best-effort apps
7. Update Kubernetes deployment annotations
8. Cilium enforces bandwidth limits via eBPF
9. Wait COOLDOWN_PERIOD_SEC before next adjustment
```

### Bandwidth Control
- **Mechanism**: Kubernetes annotations (`kubernetes.io/egress-bandwidth`)
- **Enforcement**: Cilium CNI with eBPF traffic control
- **Range**: 10-1000 Mbps (configurable)
- **Granularity**: Per-pod egress bandwidth shaping

### Metrics Collection
- **Cilium Metrics** (port 9962): General Cilium health
- **Hubble Metrics** (port 9965): L3/L4/L7 network flows
  - `hubble_http_request_duration_seconds_bucket`: HTTP latency histograms
  - `hubble_http_requests_total`: Request counters
  - `hubble_flows_processed_total`: Flow processing health
- **Prometheus**: Scrapes both endpoints, stores time-series data
- **Grafana**: Visualizes metrics with custom dashboards

## Security

### RBAC Configuration
The ML controller runs with minimal required permissions:
```yaml
# ClusterRole: ml-controller-role
permissions:
  - deployments: get, list, watch, update (for bandwidth annotations)
  - pods: get, list (for application discovery)
  
# ServiceAccount: ml-controller-sa (default namespace)
```

### Network Policies
```bash
# View Cilium network policies
kubectl get ciliumnetworkpolicies -A

# Critical app policies (L7 HTTP visibility)
- robot-factory-l7-visibility: HTTP inspection for robot-factory
- telemetry-upload-l7-visibility: HTTP inspection for telemetry-upload

# Traditional network policies
- robot-control-policy: UDP 5201 for robot control traffic
- safety-scanner-policy: TCP 5202 for safety scanning
- best-effort-policy: Allow all for best-effort apps
```

### Pod Security
- Non-root containers where possible
- Read-only root filesystem for controller
- Resource limits enforced (CPU/memory)
- No privileged escalation

## Troubleshooting

### Common Issues

**Controller not discovering applications:**
```bash
# Check controller logs for discovery output
kubectl logs -n default -l app=ml-controller | grep -A 10 "Discovered deployments"

# Verify pod labels
kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.metadata.labels.priority}{"\n"}{end}'
```

**Controller not adjusting bandwidth:**
```bash
# Check Prometheus connectivity
kubectl logs -n default -l app=ml-controller | grep "Failed to query"

# Verify RBAC permissions
kubectl auth can-i update deployments --as=system:serviceaccount:default:ml-controller-sa

# Check if Hubble metrics are available
kubectl exec -n kube-system deployment/cilium-operator -- curl localhost:9965/metrics | grep hubble_http
```

**High jitter but no bandwidth reduction:**
```bash
# Check current jitter calculation
kubectl logs -n default -l app=ml-controller --tail=50 | grep "jitter"

# Verify target thresholds
kubectl get configmap ml-controller-script -o yaml | grep TARGET_JITTER

# Check cooldown period (prevents too-frequent adjustments)
kubectl logs -n default -l app=ml-controller | grep "cooldown"
```

**Dashboard shows no data:**
```bash
# Verify Prometheus is scraping Hubble
kubectl exec -n monitoring deployment/prometheus -- wget -qO- http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="hubble")'

# Check if L7 visibility is enabled
kubectl get ciliumnetworkpolicies -A

# Verify HTTP traffic is being generated
kubectl logs -n default deployment/http-traffic-generator
```

### Debug Commands
```bash
# Controller full logs
kubectl logs -n default deployment/ml-controller -f --timestamps

# Hubble flow observation (requires hubble CLI)
kubectl exec -n kube-system ds/cilium -- hubble observe --last 100 --protocol http

# Check current bandwidth annotations
kubectl get deployments -o custom-columns="NAME:.metadata.name,NAMESPACE:.metadata.namespace,BANDWIDTH:.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth"

# Prometheus query test
kubectl exec -n monitoring deployment/prometheus -- wget -qO- \
  'http://localhost:9090/api/v1/query?query=hubble_http_requests_total' | jq
```

## Documentation

- [Learning Guide](docs/guides/LEARNING_GUIDE.md) - Kubernetes networking concepts
- [Deployment Guide](docs/setup/DEPLOYMENT_GUIDE.md) - Full deployment walkthrough
- [Monitoring Setup](docs/setup/MONITORING_STACK.md) - Prometheus/Grafana configuration
- [Containerd Build](docs/CONTAINERD_BUILD.md) - Custom containerd for bandwidth control

## Key Technologies

- **Kubernetes 1.30+**: Container orchestration platform
- **Cilium 1.18+ CNI**: eBPF-based networking with L7 visibility
- **Hubble**: Network observability for Cilium (HTTP/TCP/UDP metrics)
- **Prometheus**: Time-series metrics collection and storage
- **Grafana**: Metrics visualization and dashboards
- **Python 3.8+**: ML controller implementation

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Status**: Active Development | **Last Updated**: January 2025