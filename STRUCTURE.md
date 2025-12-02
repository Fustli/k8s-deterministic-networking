# Directory Structure (Refactored)

```
k8s-deterministic-networking/
│
├── src/                          # Python source code
│   ├── controller/
│   │   ├── flow_manager.py       # Main bandwidth controller
│   │   ├── config_loader.py      # YAML config parser
│   │   └── README.md
│   ├── probes/
│   │   ├── network_probe.py      # Active UDP/TCP prober
│   │   └── udp_server.py         # UDP echo reflector
│   └── exporters/
│       └── bandwidth_exporter.py # Prometheus exporter
│
├── deployments/                  # Kubernetes manifests
│   ├── base/                     # Control plane
│   │   ├── flow-manager.yaml
│   │   ├── flow-manager-script-configmap.yaml
│   │   ├── critical-apps-config.yaml
│   │   ├── network-probe.yaml
│   │   └── bandwidth-exporter.yaml
│   ├── critical-apps/            # Safety-critical workloads
│   │   └── workload-applications.yaml
│   ├── best-effort/              # Throttleable workloads
│   │   └── best-effort-applications.yaml
│   └── monitoring/               # Observability
│       ├── prometheus-deployment.yaml
│       ├── grafana-deployment.yaml
│       └── kube-state-metrics.yaml
│
├── k8s/                          # Additional K8s resources
│   └── policies/                 # Cilium network policies
│       ├── robot-control-policy.yaml
│       └── safety-scanner-policy.yaml
│
├── tests/                        # Test suite
│   ├── unit/                     # Algorithm tests (no deps)
│   │   ├── test_asymmetric_aimd.py
│   │   ├── test_bandwidth_algorithm.py
│   │   └── test_flow_manager_logic.py
│   ├── integration/              # Component tests (deps)
│   │   ├── test_dual_metrics.py
│   │   ├── test_network_probe_integration.py
│   │   └── test_network_probe_live.py
│   └── system/                   # E2E cluster tests
│
├── scripts/                      # Automation scripts
│   ├── deploy-flow-manager.sh
│   ├── test-traffic-iperf.sh
│   └── production/
│       └── deploy.sh
│
├── docs/                         # Documentation
│   ├── setup/
│   │   └── DEPLOYMENT_GUIDE.md
│   ├── reports/
│   │   └── BANDWIDTH_CONTROL_VERIFICATION.md
│   └── DASHBOARD_GUIDE.md
│
├── requirements/                 # Python dependencies
│   ├── requirements.txt
│   ├── requirements-prod.txt
│   └── requirements-dev.txt
│
├── README.md                     # Project overview
├── PROJECT_RESULTS.md            # Results and analysis
└── LICENSE

```

## Key Changes

### Before (Old Structure)
- `controller/` - Mixed all Python files
- `manifests/control/` - Control plane
- `manifests/applications/clients/` - Client apps
- `manifests/applications/servers/` - Server apps
- `manifests/infrastructure/` - Monitoring
- `manifests/policies/` - Network policies
- `tests/` - Mixed test types

### After (New Structure)
- `src/` - Organized by component type (controller, probes, exporters)
- `deployments/` - Organized by function (base, critical-apps, best-effort, monitoring)
- `k8s/policies/` - Separate policies directory
- `tests/` - Organized by test type (unit, integration, system)

## Benefits

1. **Clearer separation**: Source code vs deployments vs tests
2. **Logical grouping**: Related components together
3. **Easier navigation**: Purpose-based organization
4. **Better scalability**: Room for growth in each category
5. **Standard conventions**: Follows Python package structure

## Migration Note

Old paths remain in `controller/` and `manifests/` directories for backward compatibility. New deployments should use the `src/` and `deployments/` structure.
