# ML Controller

This directory contains the production-grade ML controller for Kubernetes deterministic networking.

## Files

- `ml_controller.py` - Production controller with IQR jitter calculation, EWMA smoothing, and hysteresis
- `.env` - Configuration file for controller parameters
- `.env.production` - Production environment configuration template

## Features

### Production-Grade Enhancements
- **True Jitter Calculation**: Uses Interquartile Range (Q3 - Q1) from real Hubble metrics
- **EWMA Signal Smoothing**: Reduces noise with configurable smoothing factor
- **Hysteresis Control**: Prevents oscillation with cooldown periods
- **Intelligent Throttling**: Distinguishes congestion vs distance/processing latency
- **Configuration Management**: External `.env` file configuration

### Requirements
- Real Hubble network metrics (no synthetic fallbacks)
- Prometheus with Hubble data access
- Target application generating measurable traffic

## Usage

```bash
# Deploy the production controller
kubectl apply -f ../k8s/applications/ml-controller.yaml

# Check controller logs
kubectl logs -n kube-system deployment/ml-controller -f

# Check current bandwidth
kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}'
```