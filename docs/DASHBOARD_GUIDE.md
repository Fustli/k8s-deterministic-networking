# L4 Deterministic Networking Dashboard - Implementation Guide

## 📊 Dashboard Overview

**Purpose:** Visualize L4 eBPF-based bandwidth control using packet drop rate as the control signal.

**Architecture:** Pure L4 monitoring (no Envoy L7 overhead) with <1.5ms deterministic latency.

---

## 🎯 Panel Specifications

### Row 1: Heads-Up Display (HUD)

#### Panel 1: Status Indicator (Stat)
**Title:** 🛡️ CRITICAL PROTECTION STATUS  
**Type:** Stat with background color mapping  
**Query:**
```promql
sum(rate(hubble_drop_total{reason="POLICY_DENIED"}[1m]))
```

**Thresholds:**
- **0-5 p/s:** 🟢 Green → "✅ OPTIMAL"
- **5-50 p/s:** 🟠 Orange → "⚠️ CONGESTION"  
- **>50 p/s:** 🔴 Red → "🔥 CRITICAL"

**Rationale:** Packet drops <5 p/s indicate healthy network segmentation. >50 p/s signals severe congestion requiring immediate throttling.

---

#### Panel 2: Real-Time Drop Rate (Gauge)
**Title:** 📊 Packet Drop Rate (Real-Time)  
**Type:** Gauge  
**Query:**
```promql
sum(rate(hubble_drop_total{reason="POLICY_DENIED",node=~"$node"}[1m]))
```

**Gauge Settings:**
- Min: 0, Max: 100 p/s
- Thresholds: 
  - 0-5: Green (Normal)
  - 5-20: Yellow (Elevated)
  - 20-50: Orange (High)
  - >50: Red (Critical)

---

#### Panel 3: Throttling Level (Stat)
**Title:** 🎛️ Current Throttling Level  
**Type:** Stat with value mapping  
**Query:**
```promql
kubernetes_deployment_bandwidth_limit_mbps{deployment="telemetry-upload-deployment"}
```

**Mappings:**
- **800-1000 Mbps:** 🟢 "OPEN" (No throttling)
- **50-500 Mbps:** 🔴 "THROTTLED" (Active control)
- **10-50 Mbps:** ⚫ "MIN LIMIT" (Maximum throttling)

---

### Row 2: The Control Loop Story 🎯

#### Panel 4: Drops vs. Bandwidth Intervention (THE CRITICAL PANEL)
**Title:** 🎯 THE CONTROL LOOP: Drops vs. Bandwidth Intervention  
**Type:** Time Series with Dual Y-Axis  

**Queries:**
```promql
# Query A (Left Axis - Red Line):
sum(rate(hubble_drop_total{reason="POLICY_DENIED",node=~"$node"}[1m]))

# Query B (Right Axis - Blue Step):
kubernetes_deployment_bandwidth_limit_mbps{deployment="telemetry-upload-deployment"}

# Query C (Right Axis - Purple Dash):
kubernetes_deployment_bandwidth_limit_mbps{deployment="background-traffic-generator"}
```

**Overrides Configuration:**

**Drop Rate (Query A):**
- **Color:** Red (#FF0000)
- **Axis:** Left
- **Axis Label:** "Packet Drops (p/s)"
- **Line Width:** 3px
- **Fill Opacity:** 20%
- **Unit:** pps
- **Draw Style:** Line (smooth interpolation)

**Throttle Limit (Query B):**
- **Color:** Blue (#0000FF)
- **Axis:** Right
- **Axis Label:** "Bandwidth Limit (Mbps)"
- **Line Width:** 2px
- **Line Style:** Solid step
- **Unit:** Mbps
- **Min/Max:** 0 - 1000 Mbps
- **Draw Style:** Line (step after)

**Background Limit (Query C):**
- **Color:** Purple (#800080)
- **Axis:** Right
- **Line Width:** 1px
- **Line Style:** Dashed [5,10]
- **Unit:** Mbps

**Expected Behavior:**  
When the **red line** (drops) spikes above 5 p/s, you should see the **blue line** (bandwidth) immediately step down from 1000→50 Mbps. This **inverse correlation** proves the controller is reacting correctly.

---

### Row 3: Network Health & Distribution

#### Panel 5: Drop Rate Heatmap
**Title:** 📉 Drop Rate by Node (Heatmap)  
**Type:** Heatmap  
**Query:**
```promql
sum by (node) (rate(hubble_drop_total{reason="POLICY_DENIED"}[1m]))
```

**Color Scheme:** RdYlGn (Red-Yellow-Green) reversed  
**Purpose:** Identify which worker nodes are experiencing drops. Helps detect node-specific congestion patterns.

---

#### Panel 6: Flow Processing Rate
**Title:** 🌊 Flow Processing Rate (Network Health)  
**Type:** Time Series  
**Query:**
```promql
sum by (node) (rate(hubble_flows_processed_total{type="Trace",node=~"$node"}[1m]))
```

**Unit:** flows/sec (fps)  
**Purpose:** Baseline metric showing eBPF processing capacity. Stable ~300-600 fps indicates healthy Cilium operation.

---

#### Panel 7: Drop Breakdown
**Title:** 🔬 Drop Breakdown by Reason  
**Type:** Pie Chart  
**Query:**
```promql
sum by (reason) (rate(hubble_drop_total[5m]))
```

**Purpose:** Most drops should be "POLICY_DENIED" (intentional security enforcement). Other reasons like "INVALID_SOURCE" indicate misconfigurations.

---

#### Panel 8: Controller Reaction Metric
**Title:** ⏱️ Controller Reaction Time  
**Type:** Stat  
**Query:**
```promql
changes(kubernetes_deployment_bandwidth_limit_mbps{deployment="telemetry-upload-deployment"}[10m])
```

**Interpretation:**
- **0-2 changes:** Stable (optimal)
- **3-10 changes:** Oscillating (tune EWMA_ALPHA or cooldown)
- **>10 changes:** Thrashing (increase cooldown period)

---

#### Panel 9: Bandwidth Table
**Title:** 📊 All Deployments Bandwidth Status  
**Type:** Table  
**Query:**
```promql
kubernetes_deployment_bandwidth_limit_mbps
```

**Transformations:** Hide Time, __name__, instance, job columns  
**Purpose:** At-a-glance view of which deployments are throttled.

---

## 🔧 Advanced Implementation Details

### Dashboard Variables

Add this variable to enable node filtering:

```json
{
  "name": "node",
  "type": "query",
  "datasource": "${datasource}",
  "query": "label_values(hubble_drop_total, node)",
  "multi": false,
  "includeAll": true,
  "refresh": 1
}
```

### Axis Scaling Strategy

**Problem:** Bandwidth (0-1000 Mbps) dwarfs drop rate (0-50 p/s).

**Solution:** 
1. Use **dual Y-axes** (left for drops, right for bandwidth)
2. Set **fixed max (1000)** for right axis to prevent auto-scaling
3. Use **different line widths** (drops=3px, bandwidth=2px) to maintain visibility

### PromQL Best Practices

#### Why `rate()` with `[1m]`?
- **L4 control loops need fast reaction:** 1m window balances noise reduction with responsiveness
- **Alternative:** `[30s]` for sub-minute reaction (may be noisy)

#### Why `sum by (le)` is NOT needed here?
- **L4 metrics are counters, not histograms:** `hubble_drop_total` is a simple counter
- **No bucketing required:** Unlike HTTP latency histograms, drops are scalar values

---

## 📈 Reading the Dashboard: Story Examples

### Scenario 1: Healthy Operation
```
Status: ✅ OPTIMAL (2 p/s drops)
Gauge: Green zone
Throttle: 🟢 OPEN (1000 Mbps)
Control Loop: Flat red line, flat blue line at 1000
```
**Interpretation:** Critical apps running smoothly, no intervention needed.

---

### Scenario 2: Congestion Event
```
Status: ⚠️ CONGESTION (25 p/s drops)
Gauge: Orange zone
Throttle: 🔴 THROTTLED (50 Mbps)
Control Loop: Red spike at T=0, blue drops from 1000→50 at T=5s
```
**Interpretation:** Background traffic caused congestion. Controller throttled within 5s (cooldown period). Red line should return to <5 p/s within 30-60s.

---

### Scenario 3: Oscillation (Bad Tuning)
```
Reaction Time: 15 changes in 10m
Control Loop: Sawtooth pattern (blue line bouncing 50→1000→50)
```
**Interpretation:** Controller is over-reacting. Fix:
- Increase `COOLDOWN_PERIOD_SEC` from 30→60
- Increase `EWMA_ALPHA` from 0.7→0.8 (more smoothing)
- Adjust `TARGET_DROP_RATE_PPS` threshold

---

## 🎨 Color Psychology

- **Red (Drops):** Danger/Threat - Represents undesirable packet loss
- **Blue (Bandwidth):** Control/Authority - Represents system intervention  
- **Green (Status):** Safe/Optimal - System is protecting critical traffic
- **Orange/Yellow:** Warning - Elevated but manageable

This color mapping creates an **intuitive narrative**: When red goes up, blue goes down to fight it.

---

## 🔍 Troubleshooting

### Issue: "No data" in all panels
**Check:**
```bash
kubectl logs -n kube-system -l app=ml-controller --tail=20
kubectl exec -n monitoring prometheus-xxx -- wget -qO- 'http://localhost:9090/api/v1/query?query=hubble_drop_total'
```

**Fix:** Verify Hubble metrics exporter is running on port 9965.

---

### Issue: Bandwidth metric missing
**Check:**
```bash
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations}'
```

**Fix:** ML controller must export `kubernetes_deployment_bandwidth_limit_mbps` metric. Add Prometheus scrape config for controller.

---

### Issue: Dashboard shows spikes but no controller reaction
**Check controller logs:**
```bash
kubectl logs -n kube-system -l app=ml-controller | grep "Action:"
```

**Expected:** Should see `Action: CONGESTION_THROTTLE` when drops >5 p/s.

---

## 📊 Comparison: L4 vs L7 Architecture

| Metric | L4 (eBPF-only) | L7 (with Envoy) |
|--------|----------------|-----------------|
| **Latency** | 1.9ms (P50) | 2.6ms (P50) |
| **Jitter** | 1.3ms | 2.7ms |
| **Overhead** | Kernel-only | Userspace proxy |
| **Control Signal** | Drop rate | HTTP latency |
| **Determinism** | ✅ True | ⚠️ Nondeterministic |
| **Metrics** | `hubble_drop_total` | `hubble_http_*` |

**Conclusion:** For deterministic robot control, L4 is the only viable option.

---

## 🚀 Next Steps

1. **Import dashboard JSON** to Grafana
2. **Set refresh rate** to 5 seconds
3. **Generate test load** with traffic generators
4. **Watch the control loop** react in real-time
5. **Tune thresholds** based on your workload

**Dashboard File:** `grafana-dashboard-l4-deterministic.json`
