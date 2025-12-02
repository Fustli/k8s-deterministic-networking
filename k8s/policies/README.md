# Network Policies

Cilium network policies for L7 visibility and traffic management.

## Policies

- `robot-control-policy.yaml` - L7 HTTP visibility for robot-control service
- `safety-scanner-policy.yaml` - L7 HTTP visibility for safety-scanner service

## Usage

These policies enable Hubble L7 metrics for Grafana dashboards but are **not** used for bandwidth control. The flow manager uses active probing instead.

```bash
kubectl apply -f k8s/policies/
```

## Verification

Check policy status:
```bash
kubectl get ciliumnetworkpolicies
```

View L7 flows in Hubble:
```bash
hubble observe --namespace default --protocol http
```
