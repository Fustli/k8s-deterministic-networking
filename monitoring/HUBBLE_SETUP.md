# Hubble Metrics Configuration - Next Steps

## Current Status

✅ **Completed:**
- Prometheus deployed and running
- Hubble service created in kube-system
- ML controller configured to use Prometheus
- Old test pods removed

⏳ **Pending:**
- Cilium configuration to enable Hubble metrics export
- Hubble metrics need to be scraped by Prometheus
- ML controller will then use real jitter data instead of fallback

## Problem

The ML controller attempts to query Hubble latency metrics via Prometheus, but Cilium is not currently exporting these metrics. We need to configure Cilium to:

1. Enable Hubble metrics collection
2. Export metrics on port 9091
3. Configure Prometheus to scrape these metrics

## Solution

### Step 1: Configure Cilium for Hubble Metrics

Check current Cilium configuration:

```bash
# Check if hubble metrics are enabled
kubectl get daemonset -n kube-system cilium -o yaml | grep -i "hubble"

# Or check the Cilium ConfigMap if it exists
kubectl get configmap -n kube-system cilium-config -o yaml 2>/dev/null || echo "Using helm values instead"
```

### Step 2: Enable Hubble in Cilium

If you used Helm to install Cilium, update the helm values:

```bash
# Option A: Update existing Cilium helm release
helm upgrade cilium cilium/cilium \
  --namespace kube-system \
  --set hubble.enabled=true \
  --set hubble.metrics.enabled=true \
  --set hubble.metrics.port=9091

# Then restart Cilium pods
kubectl delete pods -n kube-system -l k8s-app=cilium
kubectl delete pods -n kube-system -l k8s-app=cilium-operator
```

Or if installed via manifests:

```bash
# Option B: Add Cilium environment variable
# Edit the Cilium DaemonSet to include:
# - CILIUM_ENABLE_HUBBLE=true
# - CILIUM_HUBBLE_METRICS_PORT=9091
```

### Step 3: Verify Hubble Metrics are Exported

```bash
# Port-forward to a Cilium pod
POD=$(kubectl get pod -n kube-system -l k8s-app=cilium -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n kube-system pod/$POD 9091:9091 &

# Check if metrics endpoint is available
curl http://localhost:9091/metrics | grep hubble | head -10

# Expected output:
# hubble_flow_latency_seconds_bucket{...}
# hubble_drop_total{...}
# etc.
```

### Step 4: Update Prometheus Scrape Config

Once Hubble metrics are available, verify Prometheus is scraping them:

```bash
# Access Prometheus UI (port-forward if needed)
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# In Prometheus UI:
# 1. Go to Status → Targets
# 2. Look for "cilium" target
# 3. Should show as "UP" (green)
```

### Step 5: Verify ML Controller Gets Jitter Metrics

Once everything is configured:

```bash
# Check ML controller logs
kubectl logs -n kube-system deployment/ml-controller -f

# Expected output (instead of "No data returned"):
# 2025-11-12 17:XX:XX - INFO - Current jitter: 1.23ms
# 2025-11-12 17:XX:XX - INFO - Updated bandwidth limit to 450Mbps
```

## Current Fallback Behavior

Until Hubble metrics are configured:

- ML controller queries `up{job="cilium"}` metric
- If Cilium is healthy: returns 0.50ms (low jitter, increase bandwidth)
- If Cilium is down: returns 3.00ms (high jitter, decrease bandwidth)
- Controller will continue to function but won't use real network metrics

## Testing Hubble Query

Once Hubble metrics are available, test the query manually:

```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Test query in browser: http://localhost:9090/graph
# Paste this query:
histogram_quantile(0.95, sum(rate(hubble_flow_latency_seconds_bucket{source_pod=~"robot-control.*",protocol="UDP"}[5m])) by (le)) * 1000

# Or via curl:
curl -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=hubble_flow_latency_seconds_bucket' \
  | python3 -m json.tool | head -20
```

## Troubleshooting

### Hubble Metrics Not Available

```bash
# 1. Check Cilium pod logs
kubectl logs -n kube-system -l k8s-app=cilium --tail=20 | grep -i hubble

# 2. Check if metrics port is listening
kubectl exec -n kube-system -it <cilium-pod> -- netstat -tlnp | grep 9091

# 3. Check Cilium config
kubectl exec -n kube-system -it <cilium-pod> -- cilium status | grep hubble
```

### Prometheus Not Scraping Cilium

```bash
# Check Prometheus logs
kubectl logs -n monitoring deployment/prometheus -f | grep cilium

# Check scrape targets in Prometheus UI
# Status → Targets → cilium (should be UP)

# If DOWN, check error message
```

### ML Controller Still Using Fallback

```bash
# Check if query returns results
kubectl exec -n kube-system -it <ml-controller-pod> -- bash
curl -G 'http://prometheus.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode 'query=hubble_flow_latency_seconds_bucket'
```

## Files Related to This Setup

- **ML Controller:** `scripts/ml_controller.py`
- **ML Controller Deployment:** `manifests/apps/ml-controller.yaml`
- **Prometheus:** `monitoring/prometheus-deployment.yaml`
- **Hubble Service:** `monitoring/hubble-deployment.yaml`
- **Monitoring README:** `monitoring/README.md`

---

**Last Updated:** November 12, 2025
