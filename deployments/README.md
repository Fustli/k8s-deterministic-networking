# Kubernetes Deployments

This directory contains all Kubernetes manifests organized by purpose.

## Structure

- **base/** - Core flow manager control plane components
  - flow-manager.yaml - Main bandwidth controller
  - flow-manager-script-configmap.yaml - Controller Python code
  - critical-apps-config.yaml - SLA definitions for critical apps
  - network-probe.yaml - Active network prober
  - bandwidth-exporter.yaml - Bandwidth metrics exporter

- **critical-apps/** - Safety-critical workload applications
  - workload-applications.yaml - robot-control, safety-scanner services

- **best-effort/** - Throttleable best-effort workloads
  - best-effort-applications.yaml - telemetry-upload, erp-dashboard

- **monitoring/** - Observability stack
  - prometheus-deployment.yaml - Metrics collection
  - grafana-deployment.yaml - Visualization
  - kube-state-metrics.yaml - Kubernetes state metrics

## Deployment Order

```bash
# 1. Deploy critical workloads
kubectl apply -f critical-apps/

# 2. Deploy best-effort workloads
kubectl apply -f best-effort/

# 3. Deploy monitoring stack
kubectl apply -f monitoring/

# 4. Deploy control plane
kubectl apply -f base/
```

## Configuration

Edit `base/critical-apps-config.yaml` to adjust:
- Jitter thresholds
- Bandwidth limits
- Control parameters
- App priorities
