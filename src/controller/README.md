# Flow Manager Controller

This directory contains the production-grade controllers for Kubernetes deterministic networking.

## Files

- `flow_manager.py` - Production controller using active TCP/UDP probing to measure jitter and control bandwidth.
- `flow_manager_ebpf.py` - Alternative controller using eBPF to monitor kernel-level socket statistics for TCP and UDP.
- `bandwidth_exporter.py` - A Prometheus exporter to expose bandwidth annotations as metrics.

## Features

### `flow_manager.py` (Active Probing)
- **Real-time Metrics**: Bypasses Prometheus lag by actively probing the network path to the critical service using TCP and UDP.
- **IQR Jitter Calculation**: Calculates jitter locally from a rolling window of probe latencies.
- **Direct Action**: Dynamically patches deployment annotations to enforce bandwidth limits in near real-time.
- **Dual-Protocol Probing**: Uses both TCP and UDP probes to get a comprehensive view of network health.

### `flow_manager_ebpf.py` (eBPF-based)
- **Kernel-Level Monitoring**: Uses eBPF to track TCP RTT and UDP packet timing without application-level instrumentation.
- **Low Overhead**: Captures network statistics directly from the kernel socket layer.
- **EWMA Smoothing**: Applies an Exponentially Weighted Moving Average to latency and jitter signals to reduce noise.

## Usage

```bash
# Deploy the production controller
kubectl apply -f ../manifests/control/flow-manager.yaml

# Check controller logs
kubectl logs -n default deployment/flow-manager -f

# Check current bandwidth
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'
```