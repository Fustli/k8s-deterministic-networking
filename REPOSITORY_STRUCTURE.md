# Repository Structure

This document describes the organization and purpose of each directory in the k8s-deterministic-networking project.

## 📁 Top-Level Directories

### `manifests/` - Kubernetes Deployment Files
All YAML manifests for Kubernetes deployments, organized by purpose:

- **`manifests/policies/`** - Cilium Network Policies
  - `robot-control-policy.yaml` - Protects robot control traffic (UDP:5201)
  - `safety-scanner-policy.yaml` - Protects safety scanner traffic (TCP:5202)
  - `best-effort-policy.yaml` - Manages bandwidth for telemetry uploads (TCP:80)

- **`manifests/apps/`** - Application & Infrastructure Deployments
  - `ml-controller.yaml` - Main ML controller deployment (kube-system)
  - `ml_controller_rbac.yaml` - RBAC rules for ML controller
  - `ml-controller-configmap.yaml` - ConfigMap with ML controller scripts
  - `robot-factory-application.yaml` - Test robot factory application
  - `speedtest-server.yaml` - Network performance testing utilities

- **`manifests/examples/`** - Reference & Example Files
  - `bandwidth-annotations-example.yaml` - Example of bandwidth annotations

### `docs/` - Documentation
Primary documentation files for the project:

- `README.md` - High-level project overview
- `CONTAINERD_BUILD.md` - Historical notes on containerd setup
- `TEST_RESULTS.md` - Legacy test results reference

### `scripts/` - Python & Shell Scripts
Executable code for the project:

- `ml_controller.py` - Main ML control loop (430 lines, OOP, type-hinted)
  - Queries Hubble jitter metrics
  - Adjusts bandwidth via deployment annotations
  - Runs every 5 seconds

- `setup-monitoring.sh` - Monitoring infrastructure setup (historical)

### `test_scenarios/` - Automated Test Framework
Complete test framework for network scenarios:

- `test_runner.py` - Orchestrates all test scenarios
- `scenario_generator.py` - Generates 6 test scenarios
- `visualizer.py` - Creates markdown reports
- `visual_summary.py` - ASCII art visualizations
- `README.md` - Comprehensive test framework documentation
- `results/` - Generated test reports (7 markdown files)
- `data/` - Generated CSV/JSON test data

### `monitoring/` - [NEW] Prometheus & Hubble Setup
Reserved for monitoring infrastructure (pending implementation):

- `prometheus-deployment.yaml` - Prometheus server deployment
- `hubble-metrics.yaml` - Hubble metrics collection config
- `grafana-dashboard.json` - Grafana dashboard (future)

### `output/` - [NEW] Generated Outputs
Centralized location for test results and data:

- `results/` - Generated markdown reports
- `data/` - Raw CSV/JSON data from tests

### `docker/` - Container Images
Docker configuration for the project:

- `ml-controller/` - ML controller container
  - `Dockerfile` - Python 3.11-slim build, non-root user
  - `requirements.txt` - Python dependencies (kubernetes, prometheus-api-client)

### `tests/` - Unit Tests
Test suite for the project:

- `test_ml_controller.py` - Unit tests for ML controller logic

### `cluster-setup/` - Cluster Configuration
Cluster information and setup notes:

- `current-cluster-info.md` - Current 3-node cluster details
- `k8s-install-notes.md` - Historical Kubernetes installation notes

### `results/` - [DEPRECATED]
Legacy directory. Keeping for backward compatibility but no longer used.
New test outputs go to `output/` directory.

## 📄 Root-Level Documentation

Primary documentation files in the root directory:

- **`PROJECT_STATUS.md`** (36KB, 970 lines)
  - Complete project overview with all technical details
  - Architecture, components, deployment, troubleshooting

- **`DOCUMENTATION_INDEX.md`** (13KB, 323 lines)
  - Navigation guide with quick reference
  - Directory structure, quick start, common tasks

- **`QUICK_REFERENCE.md`** (5.6KB, 169 lines)
  - Essential commands for daily operations
  - Common kubectl, control, and monitoring commands

- **`CLEANUP_SUMMARY.md`** (6.8KB, local use only, .gitignore)
  - Historical notes on cleanup operations
  - Not tracked in GitHub

- **`LEARNING_GUIDE.md`** (42KB, local use only, .gitignore)
  - Comprehensive learning material
  - Not tracked in GitHub

## 🔄 Directory Organization Rationale

### Why Subdirectories in `manifests/`?

**Before:** All YAML files in one directory
```
manifests/
├── ml-controller.yaml
├── ml_controller_rbac.yaml
├── robot-control-policy.yaml
├── safety-scanner-policy.yaml
└── best-effort-policy.yaml
```

**After:** Organized by purpose
```
manifests/
├── apps/              (Deployments, ConfigMaps, RBAC)
├── policies/          (Cilium network policies)
└── examples/          (Reference files)
```

**Benefits:**
- Clear separation of concerns
- Easier to find related resources
- Scales well as project grows
- Better deployment workflow (apply policies first, then apps)

### Why New `monitoring/` Directory?

Reserved for upcoming Prometheus and Hubble metrics setup:
- Prometheus server deployment
- Hubble metrics collection
- Grafana dashboards

This keeps monitoring-related files organized and separate from core application files.

### Why New `output/` Directory?

Consolidates all generated test outputs:
- Test result markdown reports
- Raw CSV/JSON data
- Performance metrics

This keeps the root directory clean and makes output files easy to locate.

## 📋 File Organization Standards

### Manifest Naming Conventions

- **Policies:** `{purpose}-policy.yaml`
  - Example: `robot-control-policy.yaml`

- **Deployments:** `{app-name}.yaml`
  - Example: `ml-controller.yaml`

- **RBAC:** `{app-name}_rbac.yaml`
  - Example: `ml_controller_rbac.yaml`

- **ConfigMaps:** `{app-name}-configmap.yaml`
  - Example: `ml-controller-configmap.yaml`

### Script Naming Conventions

- **Python:** `{function}_{module}.py` or `{function}.py`
  - Example: `ml_controller.py`, `test_runner.py`

- **Shell:** `{action}-{target}.sh`
  - Example: `setup-monitoring.sh`

### Documentation Naming Conventions

- **Status:** `PROJECT_STATUS.md`
- **Navigation:** `DOCUMENTATION_INDEX.md`
- **Quick Ref:** `QUICK_REFERENCE.md`
- **README:** `README.md` (one per major section)

## 🚀 Deployment Workflow

When deploying the entire project:

1. **Apply RBAC first** (creates service account):
   ```bash
   kubectl apply -f manifests/apps/ml_controller_rbac.yaml
   ```

2. **Apply ConfigMaps** (creates config data):
   ```bash
   kubectl apply -f manifests/apps/ml-controller-configmap.yaml
   ```

3. **Apply Cilium Policies** (sets network rules):
   ```bash
   kubectl apply -f manifests/policies/
   ```

4. **Deploy Applications** (starts controllers and apps):
   ```bash
   kubectl apply -f manifests/apps/
   ```

This ordering ensures dependencies are satisfied.

## 📊 Directory Size Summary

```
monitoring/              (NEW - empty, reserved)
output/                  (NEW - empty, reserved)
cluster-setup/          8.0K  - Cluster configuration
tests/                  8.0K  - Unit test suite
docker/                16.0K  - Container images
docs/                  16.0K  - Documentation files
scripts/               28.0K  - Python/shell scripts
manifests/             44.0K  - Kubernetes YAML files
test_scenarios/       180.0K  - Test framework + results
```

## 🔍 Finding Files

| What I need | Location |
|---|---|
| Deploy ML controller | `manifests/apps/ml-controller.yaml` |
| Network policies | `manifests/policies/` |
| Python controller code | `scripts/ml_controller.py` |
| Test framework | `test_scenarios/` |
| Quick commands | `QUICK_REFERENCE.md` |
| Full technical details | `PROJECT_STATUS.md` |
| Cluster info | `cluster-setup/current-cluster-info.md` |
| Dockerfile | `docker/ml-controller/Dockerfile` |

---

**Last Updated:** November 12, 2025  
**Version:** 1.0  
**Status:** ✅ Repository Organized & Clean
