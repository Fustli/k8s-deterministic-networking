# Monitoring Setup: Prometheus + Hubble Metrics

This directory contains Kubernetes manifests for setting up Prometheus and Hubble metrics collection to enable the ML controller to query real jitter data.

## Overview

The ML controller needs real-time latency (jitter) metrics from the network to make intelligent bandwidth adjustment decisions. This is provided by:

1. **Cilium + Hubble** - Network observability layer that collects flow metrics
2. **Prometheus** - Time-series database that stores and queries metrics
3. **ML Controller** - Queries Prometheus for jitter data and adjusts bandwidth

## Architecture

```
┌─────────────────────────────────────┐
│   Cilium Hubble (kube-system)       │
│   - Flow latency metrics            │
│   - Packet loss tracking            │
│   - L4 protocol statistics          │
└──────────────┬──────────────────────┘
               │ metrics endpoint :9091
               ↓
┌─────────────────────────────────────┐
│  Prometheus (monitoring namespace)  │
│  - Scrapes Hubble metrics           │
│  - Time-series storage (30 days)    │
│  - PromQL query engine              │
└──────────────┬──────────────────────┘
               │ HTTP API :9090
               ↓
┌─────────────────────────────────────┐
│   ML Controller (kube-system)       │
│   - Queries Prometheus for jitter   │
│   - Calculates bandwidth decisions  │
│   - Patches deployment annotations  │
└─────────────────────────────────────┘
```

## Prerequisites

- Cilium CNI installed with bandwidth manager enabled (✅ Already configured)
- Kubernetes 1.20+ (✅ You have 1.30.14)
- kubectl access to the cluster

## Deployment Steps

### Step 1: Verify Cilium Hubble Metrics are Available

First, check that Cilium has Hubble metrics enabled:

```bash
# Check if cilium pods are exporting metrics on port 9091
kubectl port-forward -n kube-system daemonset/cilium 9091:9091 &
curl http://localhost:9091/metrics | grep hubble

# Expected output: hubble_* metrics (latency, drops, etc.)
```

### Step 2: Deploy Prometheus

```bash
# Create monitoring namespace and deploy Prometheus
kubectl apply -f prometheus-deployment.yaml

# Wait for Prometheus to be ready
kubectl wait --for=condition=ready pod \
  -l app=prometheus -n monitoring \
  --timeout=120s

# Verify Prometheus is running
kubectl get pods -n monitoring
```

### Step 3: Deploy Hubble Metrics Service

```bash
# Create Hubble service for Prometheus scraping
kubectl apply -f hubble-deployment.yaml

# Verify service is created
kubectl get svc -n kube-system | grep hubble
```

### Step 4: Verify Prometheus is Scraping Metrics

```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Open browser to http://localhost:9090

# In Prometheus UI:
# 1. Go to Status → Targets
# 2. Verify "cilium" and "hubble" targets are "UP"
# 3. Go to Graph tab and search for "hubble_flow_latency_seconds"
```

### Step 5: Verify ML Controller Can Query Metrics

```bash
# Check ML controller logs for successful metric queries
kubectl logs -n kube-system deployment/ml-controller -f

# Expected output:
# "Current jitter: X.XXms"  (not "0.50ms fallback")
```

## Accessing Prometheus UI

### Option 1: Port-Forward (Local Development)

```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Then visit http://localhost:9090
```

### Option 2: NodePort (Access from Any Machine on Network)

```bash
# Get the node port
kubectl get svc -n monitoring prometheus-external
# NodePort will be 30090

# Access from any machine:
# http://<any-node-ip>:30090
```

### Option 3: Port-Forward from Remote

```bash
# If running this from a remote machine
ssh -L 9090:localhost:9090 user@cluster-master kubectl port-forward -n monitoring svc/prometheus 9090:9090
```

## Querying Hubble Metrics in Prometheus

### Example Queries

**1. Current jitter (latency) for robot-control traffic:**
```promql
histogram_quantile(0.95, sum(rate(
  hubble_flow_latency_seconds_bucket{
    source_pod=~"robot-control.*",
    protocol="UDP"
  }[1m]
)) by (le)) * 1000
```

**2. Packet loss rate:**
```promql
rate(hubble_drop_total[5m])
```

**3. TCP connections per second:**
```promql
rate(hubble_tcp_flags_total{flags="SYN"}[1m])
```

**4. Average latency by source pod:**
```promql
histogram_quantile(0.50, sum(rate(
  hubble_flow_latency_seconds_bucket[5m]
)) by (source_pod, le))
```

## Prometheus Configuration

The Prometheus deployment scrapes:

- **Cilium Daemonset** - Network metrics (port 9091)
- **Kubernetes API Server** - Cluster metrics
- **Node Exporter** (if installed) - Host metrics

Metrics are retained for **30 days** with TSDB compression.

## Troubleshooting

### Prometheus Targets Show "DOWN"

```bash
# Check Prometheus logs
kubectl logs -n monitoring deployment/prometheus -f

# Verify Cilium is exporting metrics
kubectl port-forward -n kube-system daemonset/cilium 9091:9091
curl http://localhost:9091/metrics | head -20
```

### ML Controller Still Reports "0.50ms" Fallback

```bash
# 1. Verify Prometheus is accessible
kubectl get svc -n monitoring

# 2. Check if ML controller environment variable is set
kubectl get deployment -n kube-system ml-controller -o yaml | grep PROMETHEUS_URL

# 3. Test connectivity from ML controller pod
kubectl exec -it -n kube-system deployment/ml-controller -- bash
curl http://prometheus:9090/api/v1/query?query=up
```

### High Memory Usage

```bash
# Adjust storage retention in prometheus-deployment.yaml
# Change: --storage.tsdb.retention.time=30d
# To: --storage.tsdb.retention.time=7d

# Then redeploy
kubectl apply -f prometheus-deployment.yaml
```

## Performance Impact

- **Prometheus CPU**: ~100-250m (with 1-minute scrape interval)
- **Prometheus Memory**: 512Mi - 1Gi (for 30 days retention)
- **Cilium Metrics Overhead**: <5% (already running for other monitoring)

## Cleanup

To remove monitoring infrastructure:

```bash
kubectl delete -f prometheus-deployment.yaml
kubectl delete -f hubble-deployment.yaml
kubectl delete namespace monitoring
```

## Next Steps

After Prometheus and Hubble are deployed:

1. Update ML controller environment variable if needed
2. Verify real jitter metrics appear in logs
3. Monitor Prometheus disk usage
4. Optional: Deploy Grafana for visualization

---

**Related Files:**
- ML Controller: `scripts/ml_controller.py`
- ML Controller Deployment: `manifests/apps/ml-controller.yaml`
- Cilium Policies: `manifests/policies/`

**Last Updated:** November 12, 2025
