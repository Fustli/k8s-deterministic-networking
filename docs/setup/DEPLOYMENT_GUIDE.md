# Deployment Guide

Complete guide for deploying the K3s Deterministic Networking system.

## 📋 Prerequisites

- Kubernetes 1.30+ (v1.30.14+)
- Cilium CNI 1.18.4+
- BandwidthManager enabled
- kubectl CLI
- 3+ node cluster (1 master, 2+ workers recommended)

## 🚀 Quick Deployment

### Option 1: Using Kustomize (Recommended)

```bash
# 1. Deploy base infrastructure
kubectl apply -k infrastructure/

# 2. Deploy application (dev environment)
kubectl apply -k deploy/kustomize/overlays/dev

# 3. Verify deployment
kubectl get pods -A
kubectl get svc -A
```

### Option 2: Using Helm (Cilium)

```bash
# 1. Enable Cilium metrics via Helm
helm upgrade cilium cilium/cilium -n kube-system \
  --reuse-values \
  --set prometheus.enabled=true

# 2. Deploy infrastructure
kubectl apply -f infrastructure/monitoring/

# 3. Deploy applications
kubectl apply -f deploy/kustomize/base/
```

### Option 3: Full Manual Deployment

```bash
# 1. Configure Cilium
kubectl patch configmap cilium-config -n kube-system \
  -p '{"data":{"enable-prometheus":"true"}}'

# 2. Update Hubble Relay
kubectl patch deployment hubble-relay -n kube-system \
  --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--metrics-listen-address=:9965"}]'

# 3. Deploy Prometheus
kubectl apply -f infrastructure/monitoring/prometheus-deployment.yaml

# 4. Deploy controllers
kubectl apply -f deploy/kustomize/base/flow-manager.yaml
kubectl apply -f deploy/kustomize/base/flow-manager-configmap.yaml
kubectl apply -f deploy/kustomize/base/flow_manager_rbac.yaml

# 5. Deploy workloads
kubectl apply -f deploy/kustomize/base/robot-factory-application.yaml
kubectl apply -f deploy/kustomize/base/speedtest-server.yaml

# 6. Deploy traffic generation
kubectl apply -f manifests/test-clients.yaml

# 7. Deploy policies
kubectl apply -f infrastructure/policies/
```

## ✅ Verification

### Check All Components

```bash
# 1. Verify Cilium is running
kubectl get daemonset -n kube-system cilium
kubectl get pods -n kube-system -l k8s-app=cilium

# 2. Verify Hubble Relay
kubectl get deployment -n kube-system hubble-relay
kubectl logs -n kube-system -l app=hubble-relay

# 3. Verify Prometheus
kubectl get deployment -n monitoring prometheus
kubectl logs -n monitoring -l app=prometheus

# 4. Verify Flow Manager
kubectl get deployment -n kube-system flow-manager
kubectl logs -n kube-system -l app=flow-manager

# 5. Verify traffic clients
kubectl get pods -n default -l traffic-type
```

### Verify Metrics Flow

```bash
# 1. Check Cilium metrics are being exported
curl http://$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'):9962/metrics | head -20

# 2. Check Hubble Relay metrics
kubectl exec -n kube-system deployment/hubble-relay -- curl localhost:9965/metrics | head -20

# 3. Query Prometheus
PROM_POD=$(kubectl get pod -n monitoring -l app=prometheus -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n monitoring $PROM_POD -- curl localhost:9090/api/v1/query?query=up

# 4. Check Flow manager logs
kubectl logs -n kube-system -l app=flow-manager | tail -20
```

### Verify Traffic Generation

```bash
# Check traffic clients are running
kubectl get pods -n default -l traffic-type

# Check traffic is being generated
kubectl exec -n default deployment/http-client -- tail -20 /tmp/requests.log

# Verify Cilium is capturing flows
kubectl exec -n kube-system -it daemonset/cilium -c cilium-agent -- cilium status | grep -i flows
```

## 🔧 Configuration

### Flow Manager Configuration

Edit `deploy/kustomize/base/flow-manager-configmap.yaml`:

```yaml
data:
  PROMETHEUS_URL: "http://prometheus:9090"
  JITTER_THRESHOLD: "50"  # milliseconds
  BANDWIDTH_MIN: "1Mbps"
  BANDWIDTH_MAX: "1000Mbps"
  UPDATE_INTERVAL: "5"  # seconds
```

### Environment-Specific Overlays

**Development** (`deploy/kustomize/overlays/dev/`):
- 1 replica of flow-manager
- Always pull images
- Debug logging enabled

**Production** (`deploy/kustomize/overlays/prod/`):
- 3 replicas of flow-manager (HA)
- IfNotPresent image pull policy
- Strict resource limits

## 🐛 Troubleshooting

### Cilium Metrics Not Exporting

```bash
# 1. Check if Prometheus is enabled in Cilium
kubectl get cm -n kube-system cilium-config -o jsonpath='{.data.enable-prometheus}'
# Should output: "true"

# 2. Verify port 9962 is accessible
kubectl get daemonset -n kube-system cilium -o yaml | grep -A5 "hostPort"

# 3. Check Cilium pod logs
kubectl logs -n kube-system daemonset/cilium -c cilium-agent | grep -i prometheus
```

### Hubble Relay Not Exporting Metrics

```bash
# 1. Check if metrics listener is enabled
kubectl get deployment -n kube-system hubble-relay -o yaml | grep "metrics-listen-address"

# 2. Test metrics endpoint
kubectl exec -n kube-system deployment/hubble-relay -- curl localhost:9965/metrics

# 3. Check relay logs
kubectl logs -n kube-system deployment/hubble-relay
```

### Prometheus Targets Down

```bash
# 1. Check Prometheus scrape configuration
kubectl get cm -n monitoring prometheus-config -o yaml | grep -A10 "scrape_configs"

# 2. Query Prometheus targets API
kubectl exec -n monitoring deployment/prometheus -- \
  curl localhost:9090/api/v1/targets | jq '.data.activeTargets[]'

# 3. Verify network connectivity
kubectl exec -n monitoring deployment/prometheus -- \
  curl -v http://172.16.0.59:9962/metrics 2>&1 | head -20
```

### Flow Manager Not Updating Bandwidth

```bash
# 1. Check controller logs
kubectl logs -n kube-system deployment/flow-manager -f

# 2. Verify Prometheus connectivity
kubectl exec -n kube-system deployment/flow-manager -- \
  curl http://prometheus:9090/api/v1/query?query=up

# 3. Check deployment annotations
kubectl get deployment robot-factory-application -o yaml | grep -i bandwidth

# 4. Verify ConfigMap is mounted
kubectl exec -n kube-system deployment/flow-manager -- ls -la /etc/config/
```

## 📊 Monitoring

### Access Prometheus

```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Open in browser: http://localhost:9090
```

### Key Queries

```promql
# Flow rate
rate(cilium_flows_processed_total[1m])

# Bandwidth utilization
cilium_bandwidth_*

# Policy decisions
rate(cilium_policy_verdict[1m])

# Connection count
cilium_conntrack_gc_*
```

## 🔄 Updates

### Update Cilium Configuration

```bash
# Update via ConfigMap
kubectl patch cm cilium-config -n kube-system \
  -p '{"data":{"key":"value"}}'

# Restart Cilium pods to apply
kubectl rollout restart daemonset/cilium -n kube-system
kubectl rollout status daemonset/cilium -n kube-system
```

### Update Flow Manager

```bash
# Update via image tag
kubectl set image deployment/flow-manager -n kube-system \
  flow-manager=flow-manager:v1.1 \
  --record

# Monitor rollout
kubectl rollout status deployment/flow-manager -n kube-system
kubectl rollout history deployment/flow-manager -n kube-system
```

## 🗑️ Cleanup

```bash
# Remove all deployments
kubectl delete -k deploy/kustomize/overlays/dev

# Remove infrastructure
kubectl delete -k infrastructure/

# Remove traffic generation (if separate)
kubectl delete -f manifests/test-clients.yaml

# Remove all policies
kubectl delete -f infrastructure/policies/
```

## 📝 Next Steps

1. **Configure Overlays**: Customize `deploy/kustomize/overlays/` for your environment
2. **Set Thresholds**: Adjust Flow manager parameters in ConfigMap
3. **Add Tests**: Add integration tests in `tests/integration/`
4. **Monitor**: Set up Grafana dashboards for visualization
5. **Document**: Update guides with your specific configuration

---

**For more information**, see:
- [Architecture Guide](../architecture/)
- [Setup Guides](./SETUP_SUMMARY.md)
- [Project Status](../PROJECT_STATUS.md)
