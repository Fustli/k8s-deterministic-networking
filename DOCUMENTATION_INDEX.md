# K8s Deterministic Networking - Documentation Index

Welcome! This is your complete guide to the ML-driven network controller project.

## 📋 Quick Navigation

### For First-Time Users
1. **Start here:** [`docs/README.md`](docs/README.md) - High-level project overview
2. **Project status:** [`PROJECT_STATUS.md`](PROJECT_STATUS.md) - Complete status report (969 lines)
3. **Quick reference:** [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md) - Essential commands and parameters

### For Developers
- **ML Controller implementation:** [`scripts/ml_controller.py`](scripts/ml_controller.py) - Main control loop (OOP, type-hinted)
- **Test framework guide:** [`test_scenarios/README.md`](test_scenarios/README.md) - How to run and customize tests
- **Network policies:** [`manifests/*-policy.yaml`](manifests/) - Cilium policy definitions
- **Deployment YAML:** [`manifests/ml-controller.yaml`](manifests/ml-controller.yaml) - Kubernetes deployment config

### For Operations
- **Cluster info:** [`cluster-setup/current-cluster-info.md`](cluster-setup/current-cluster-info.md) - 3-node cluster details
- **Troubleshooting:** See PROJECT_STATUS.md Section 9
- **Monitoring:** Use `QUICK_REFERENCE.md` commands section

### For Testing
- **Test scenarios:** [`test_scenarios/`](test_scenarios/) - Run full test pipeline
- **View results:** [`test_scenarios/results/`](test_scenarios/results/) - Generated reports with metrics
- **See visualizations:** `python3 test_scenarios/visual_summary.py`

---

## 🗂️ Directory Structure

```
/home/ubuntu/k8s-deterministic-networking/
│
├── 📄 PROJECT_STATUS.md              ← Read this first for complete overview
├── 📄 QUICK_REFERENCE.md             ← Daily operations commands
├── 📄 DOCUMENTATION_INDEX.md          ← This file
│
├── 📁 docs/
│   ├── README.md                      High-level project description
│   ├── CONTAINERD_BUILD.md            containerd setup notes
│   └── TEST_RESULTS.md                Legacy test results reference
│
├── 📁 cluster-setup/
│   ├── current-cluster-info.md        Kubernetes cluster configuration
│   └── k8s-install-notes.md          Historical setup notes
│
├── 📁 manifests/                      All Kubernetes YAML files
│   ├── policies/                      Cilium network policies
│   │   ├── robot-control-policy.yaml  ✅ UDP:5201 QoS protection
│   │   ├── safety-scanner-policy.yaml ✅ TCP:5202 QoS protection
│   │   └── best-effort-policy.yaml    ✅ TCP:80 bandwidth management
│   ├── apps/                          Deployment & app configs
│   │   ├── ml-controller.yaml         ✅ ML controller deployment
│   │   ├── ml_controller_rbac.yaml    ✅ RBAC for kube-system
│   │   ├── ml-controller-configmap.yaml ConfigMap with scripts
│   │   ├── robot-factory-application.yaml ✅ Test application
│   │   └── speedtest-server.yaml      Network test utilities
│   └── examples/                      Reference & example files
│       └── bandwidth-annotations-example.yaml Annotation reference
│
├── 📁 scripts/
│   ├── ml_controller.py               ✅ Main ML controller (OOP)
│   └── setup-monitoring.sh            Monitoring setup
│
├── 📁 docker/
│   └── ml-controller/
│       ├── Dockerfile                 ✅ Python 3.11-slim build
│       └── requirements.txt           Dependencies (kubernetes, prometheus-api-client)
│
├── 📁 test_scenarios/                 ✅ Complete test framework
│   ├── README.md                      Comprehensive test guide
│   ├── scenario_generator.py          6 scenario generators
│   ├── test_runner.py                 Full pipeline orchestrator
│   ├── visualizer.py                  Markdown report generator
│   ├── visual_summary.py              ASCII art visualizer
│   ├── results/                       Generated reports (7 markdown)
│   └── data/                          Generated CSV/JSON files

├── 📁 monitoring/                     [NEW] Prometheus & Hubble setup
│   ├── prometheus-deployment.yaml     (Pending implementation)
│   └── hubble-metrics.yaml            (Pending implementation)

├── 📁 output/                         [NEW] Generated test outputs
│   ├── results/                       Test result summaries
│   └── data/                          Raw test data files
│
├── 📁 tests/
│   ├── baseline-tests.sh              Test execution scripts
│   ├── test_ml_controller.py          Unit tests for control logic
│   └── [flannel baseline test YAMLs]
│
└── 📁 results/
    └── flannel-baseline/              [Historical: Old test results]
```

---

## 🚀 Getting Started in 5 Minutes

### 1. Verify Cluster is Running
```bash
kubectl get nodes -o wide
# Expected: 3 nodes with containerd runtime
```

### 2. Check ML Controller Status
```bash
kubectl get deployment -n kube-system ml-controller
# Expected: 1/1 Ready

kubectl logs -n kube-system deployment/ml-controller --tail=5
# Expected: "Current jitter: X.XXms" lines
```

### 3. Run Test Scenarios
```bash
cd test_scenarios
python3 test_runner.py
# Expected: "✅ TEST PIPELINE COMPLETED SUCCESSFULLY!"
```

### 4. View Results
```bash
cat results/SUMMARY.md          # Read summary analysis
python3 visual_summary.py       # Display ASCII visualizations
ls -lh results/                 # See all generated reports
```

### 5. Check Bandwidth Patching
```bash
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations}'
# Expected: kubernetes.io/egress-bandwidth: "XXX M" (value changing over time)
```

---

## 🎯 Key Features

| Feature | Status | Location |
|---------|--------|----------|
| **ML Controller** | ✅ Deployed & Running | `scripts/ml_controller.py` |
| **QoS via Cilium** | ✅ Active | `manifests/policies/` |
| **Bandwidth Control** | ✅ Patching | `manifests/apps/ml-controller.yaml` |
| **Test Framework** | ✅ Complete | `test_scenarios/` |
| **Prometheus Metrics** | ⚠️ Pending Setup | `monitoring/` (NEW) |
| **Hubble Metrics** | ⚠️ Pending Setup | `monitoring/` (NEW) |
| **HA Deployment** | ⏳ Pending | Scale to 2+ replicas |
| **Production Hardening** | ⏳ Pending | See PROJECT_STATUS.md §5.2 |

---

## 📊 Test Scenarios Summary

Six realistic network conditions are simulated:

| Scenario | Jitter Range | Bandwidth Profile | Key Validation |
|----------|---|---|---|
| **Normal Operation** | 0.30-0.38ms | Growing (100→700Mbps) | ✅ Aggressive increase |
| **Jitter Spike** | 0.50→3.00→1.00ms | Rapid down then up | ✅ Correct spike response |
| **Sustained Load** | 1.00→5.70ms | Sharp drop to 10Mbps | ✅ Reaches floor |
| **Oscillation** | 1.00-1.70ms | Minimal changes | ✅ Deadband behavior |
| **Degradation** | 0.50→5.00ms | 3-stage reduction | ✅ Progressive throttle |
| **Recovery** | 5.00→0.50ms | 3-stage restoration | ✅ Gradual increase |

**Run tests:** `cd test_scenarios && python3 test_runner.py`  
**View results:** `cat results/SUMMARY.md` or `python3 visual_summary.py`

---

## 🔧 Control Loop Parameters

Located in: `scripts/ml_controller.py`

```python
TARGET_JITTER_MS = 1.0              # Bandwidth increases if below this
MIN_BANDWIDTH_MBPS = 10             # Minimum allocation
MAX_BANDWIDTH_MBPS = 1000           # Maximum allocation
DECREASE_STEP_MBPS = 50             # Reduction on high jitter
INCREASE_STEP_MBPS = 10             # Growth on low jitter
```

**Decision Logic:**
- Jitter high? → Reduce bandwidth (protect critical flows)
- Jitter low? → Increase bandwidth (maximize throughput)
- Interval: Check every 5 seconds

---

## 📖 Documentation Files

| File | Purpose | Audience | Length |
|------|---------|----------|--------|
| `PROJECT_STATUS.md` | Complete project overview with all details | Everyone | 969 lines |
| `QUICK_REFERENCE.md` | Essential commands and parameters | Operations | 169 lines |
| `docs/README.md` | High-level project description | New users | ~100 lines |
| `test_scenarios/README.md` | Test framework guide | Developers | ~300 lines |
| `cluster-setup/current-cluster-info.md` | Cluster configuration | Operators | ~50 lines |

---

## ✅ Deployment Status

```
KUBERNETES CLUSTER:        ✅ Running (3 nodes, v1.30.14)
CILIUM CNI:               ✅ Active (v1.18.3, bandwidthManager enabled)
ML CONTROLLER:            ✅ Running (kube-system, 1/1 Ready)
NETWORK POLICIES:         ✅ Valid (3 CiliumNetworkPolicy objects)
CONTAINER RUNTIME:        ✅ containerd v1.7.28
TEST FRAMEWORK:           ✅ Complete (6 scenarios, 7 reports)
PROMETHEUS/HUBBLE:        ⚠️  Fallback (needs setup)
PRODUCTION HARDENING:     ⏳ Pending (hysteresis, smoothing, HA)
```

---

## 🔍 Common Tasks

### Monitor Controller in Real-Time
```bash
kubectl logs -n kube-system deployment/ml-controller -f
```

### Check Current Bandwidth
```bash
kubectl get deploy telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'
```

### Run All Tests
```bash
cd test_scenarios && python3 test_runner.py
```

### View Test Summary
```bash
cat test_scenarios/results/SUMMARY.md
```

### Verify Policies Enforcing
```bash
kubectl get cnp --all-namespaces -o wide
```

### Check Cluster Health
```bash
kubectl get nodes -o wide
kubectl get all -n kube-system | grep -E "(cilium|ml-controller)"
```

---

## 🚨 Troubleshooting Quick Links

- **Controller pod not running?** → See PROJECT_STATUS.md §9.1
- **Bandwidth not updating?** → See PROJECT_STATUS.md §9.2
- **Jitter always 0.50ms?** → See PROJECT_STATUS.md §9.3
- **Policies not enforcing?** → See PROJECT_STATUS.md §9 (general)
- **Emergency pause controller?** → `kubectl scale deployment ml-controller -n kube-system --replicas=0`

---

## 📚 Further Reading

### Inside This Repository
1. **Full status report** → `PROJECT_STATUS.md` (comprehensive, 969 lines)
2. **Quick operations guide** → `QUICK_REFERENCE.md` (essential commands)
3. **Test framework details** → `test_scenarios/README.md` (customization guide)
4. **ML controller code** → `scripts/ml_controller.py` (implementation details)

### External References
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Cilium Docs](https://docs.cilium.io/)
- [containerd Docs](https://containerd.io/)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)

---

## 🎓 Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│ Kubernetes Cluster (3 nodes, containerd runtime)   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Cilium CNI with BandwidthManager (eBPF)           │
│  └─ UDP/TCP priority queuing                       │
│                                                     │
│  ML Controller (kube-system)                        │
│  ├─ Queries: Hubble jitter metrics                 │
│  ├─ Decides: Bandwidth increase/decrease           │
│  └─ Patches: Deployment annotations                │
│                                                     │
│  Critical Apps (QoS Protected)                      │
│  ├─ robot-control (UDP:5201)                       │
│  └─ safety-scanner (TCP:5202)                      │
│                                                     │
│  Best-Effort Apps (Bandwidth Managed)              │
│  ├─ telemetry-upload (TCP:80)  ← Patched by ML    │
│  └─ erp-dashboard (TCP:80)                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 📞 Support

**Need help?**
1. Check `QUICK_REFERENCE.md` for common commands
2. Read `PROJECT_STATUS.md` §9 for troubleshooting
3. Review `test_scenarios/results/SUMMARY.md` for insights
4. Run `kubectl logs -n kube-system deployment/ml-controller` for diagnostic info

**Found an issue?**
- Check current logs: `kubectl logs -n kube-system deployment/ml-controller --tail=100`
- Review test results: `cat test_scenarios/results/SUMMARY.md`
- Verify policies: `kubectl get cnp --all-namespaces -o wide`

---

## 📅 Project Timeline

| Phase | Status | Date |
|-------|--------|------|
| Architecture Design | ✅ Complete | Session 1 |
| ML Controller Development | ✅ Complete | Session 2 |
| Cilium Policy Deployment | ✅ Complete | Session 2 |
| containerd Migration | ✅ Complete | Session 3 |
| Live Cluster Testing | ✅ Complete | Session 4 |
| Test Scenarios Framework | ✅ Complete | Session 5 |
| Production Hardening | ⏳ Pending | Next |
| Live Performance Tests | ⏳ Pending | Next |
| Registry Deployment | ⏳ Pending | Future |

---

**Last Updated:** November 11, 2025  
**Version:** 1.0  
**Status:** ✅ Project Functional, Test Framework Complete

For the most comprehensive information, start with [`PROJECT_STATUS.md`](PROJECT_STATUS.md).
