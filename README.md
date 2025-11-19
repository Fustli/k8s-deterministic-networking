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
├── config/                  # Environment configuration
│   ├── .env                 # Development configuration
│   ├── .env.production      # Production configuration template
│   └── README.md           # Configuration documentation
├── controller/              # Production ML Controller
│   ├── ml_controller.py     # Main production controller
│   ├── requirements.txt     # Python dependencies
│   └── README.md           # Controller documentation
├── k8s/                     # Kubernetes manifests  
│   ├── applications/        # Application deployments
│   ├── infrastructure/      # Monitoring stack (Prometheus, Grafana)
│   ├── policies/           # Network policies
│   ├── security/           # Security configurations
│   └── traffic/            # Traffic management
├── scripts/                 # Operational scripts
│   └── production/         # Production deployment automation
├── tests/                   # Comprehensive test suite
├── tools/                   # Development/debug utilities
└── docs/                   # Technical documentation
    ├── setup/              # Deployment and setup guides
    └── reports/            # Technical analysis reports
```
├── tools/                # Development/testing tools
├── scripts/              # Automation scripts
└── docs/                 # Documentation & reports
```

## Quick Start

### Prerequisites
- Kubernetes 1.28+ cluster
- Cilium CNI with eBPF enabled
- Prometheus for metrics collection

### Deploy the System
```bash
# 1. Deploy infrastructure components
kubectl apply -f k8s/infrastructure/

# 2. Apply network policies  
kubectl apply -f k8s/policies/

# 3. Deploy ML controller
kubectl apply -f k8s/applications/

# 4. Start traffic generation (optional)
kubectl apply -f k8s/traffic/
```

### Verify Deployment
```bash
# Check controller status
kubectl logs -n kube-system -l app=ml-controller -f

# Monitor bandwidth adjustments
kubectl get deployment telemetry-upload-deployment -o yaml | grep bandwidth

# Access Grafana dashboards
kubectl port-forward -n monitoring svc/grafana 3000:3000
```

## Configuration

The controller uses environment variables and `.env` file configuration:

### Configuration File (`.env`)
```bash
# Prometheus/Monitoring
PROMETHEUS_URL=http://prometheus-server:9090
TARGET_APPLICATION=robot-factory

# Control Thresholds
TARGET_JITTER_MS=2.0
TARGET_LATENCY_MS=10.0

# Bandwidth Limits
MIN_BANDWIDTH_MBPS=10
MAX_BANDWIDTH_MBPS=1000

# EWMA Smoothing
EWMA_ALPHA=0.7

# Hysteresis
COOLDOWN_PERIOD_SEC=30
```

### Deployment
```bash
# Deploy the production controller
kubectl apply -f k8s/applications/ml-controller.yaml
```

## Monitoring

### Grafana Dashboards
- **Controller Metrics**: Bandwidth adjustments, jitter measurements
- **Network QoS**: Flow latencies, packet drops, throughput
- **System Health**: Controller status, failover events

### Key Metrics
```promql
# Current bandwidth allocation
kubernetes_bandwidth_limit_mbps

# Network jitter (95th percentile)  
histogram_quantile(0.95, hubble_flow_latency_seconds_bucket)

# Controller health
up{job="ml-controller"}
```

## Testing

### Run Full Test Suite
```bash
cd tests/
python3 run_tests.py --verbose --coverage
```

### Manual Testing Tools
```bash
# Test bandwidth control
python3 tools/test_bandwidth_control.py --target-jitter 2.0

# Test decrease scenarios  
python3 tools/test_decrease.py

# Comprehensive validation
python3 tools/comprehensive_test.py
```

## Production Readiness

### Implemented Features
- [x] **Comprehensive Test Suite** (200+ tests)
- [x] **High Availability** (Leader election, multi-replica)
- [x] **Monitoring & Alerting** (Grafana dashboards, PagerDuty)
- [x] **Security Hardening** (RBAC, Network policies, Pod security)

### Operational Procedures
- Health checks and readiness probes
- Graceful shutdown and failover
- Backup and disaster recovery
- Performance monitoring and optimization

## Security

### Network Policies
```bash
# View applied policies
kubectl get networkpolicies -A

# Critical app isolation
kubectl describe networkpolicy robot-control-policy
```

### RBAC Permissions
```bash
# Controller permissions
kubectl describe clusterrole cilium-policy-patcher

# Service account details
kubectl describe serviceaccount ml-controller-sa -n kube-system
```

## Troubleshooting

### Common Issues

**Controller not adjusting bandwidth:**
```bash
# Check Prometheus connectivity
kubectl logs -n kube-system -l app=ml-controller | grep "Failed to query"

# Verify RBAC permissions
kubectl auth can-i update deployments --as=system:serviceaccount:kube-system:ml-controller-sa
```

**High jitter not reducing bandwidth:**
```bash
# Check control parameters
kubectl get configmap ml-controller-script -n kube-system -o yaml | grep TARGET_JITTER

# Monitor control loop
kubectl logs -n kube-system -l app=ml-controller --tail=20
```

### Debug Commands
```bash
# Controller logs with timestamps
kubectl logs -n kube-system deployment/ml-controller -f --timestamps

# Network flow observation
kubectl exec -n kube-system deployment/hubble-relay -- hubble observe --last 100

# Bandwidth verification
kubectl get pods -o custom-columns="NAME:.metadata.name,BANDWIDTH:.metadata.annotations.kubernetes\.io/egress-bandwidth"
```

## Documentation

- [Architecture Guide](docs/guides/LEARNING_GUIDE.md)
- [Deployment Guide](docs/setup/DEPLOYMENT_GUIDE.md)
- [Implementation Reports](docs/reports/)
- [API Documentation](controller/README.md)

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Run tests: `python3 tests/run_tests.py`
4. Commit changes: `git commit -m 'Add amazing feature'`
5. Push to branch: `git push origin feature/amazing-feature`
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Status**: Production Ready | **Version**: 2.0 | **Last Updated**: November 18, 2025