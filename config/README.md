# Configuration Directory

This directory contains environment configuration files for the Flow Manager.

## Files

### `.env`
Development/testing configuration with default values. Used when running the controller locally or in development environments.

### `.env.production`
Production configuration template. Copy and customize this file with your production-specific values before deploying.

## Configuration Variables

### Prometheus/Monitoring
- `PROMETHEUS_URL`: Prometheus server endpoint
- `TARGET_APPLICATION`: Target application name for metrics filtering

### Control Parameters  
- `TARGET_JITTER_MS`: Target jitter threshold in milliseconds
- `TARGET_LATENCY_MS`: Target latency threshold in milliseconds
- `EWMA_ALPHA`: Smoothing factor for EWMA (0.0-1.0)

### Bandwidth Control
- `MIN_BANDWIDTH_MBPS`: Minimum bandwidth limit
- `MAX_BANDWIDTH_MBPS`: Maximum bandwidth limit
- `AGGRESSIVE_DECREASE_MBPS`: Bandwidth reduction for high jitter
- `GENTLE_DECREASE_MBPS`: Bandwidth reduction for mild congestion
- `INCREASE_STEP_MBPS`: Bandwidth increase step size

### Timing & Hysteresis
- `CONTROL_INTERVAL_SEC`: Main control loop interval
- `COOLDOWN_PERIOD_SEC`: Hysteresis cooldown period
- `CRITICAL_JITTER_MULTIPLIER`: Threshold multiplier for critical jitter

### Kubernetes
- `DEPLOYMENT_NAME`: Target deployment name
- `NAMESPACE`: Kubernetes namespace
- `BANDWIDTH_ANNOTATION`: Annotation key for bandwidth control

## Usage

The controller automatically loads configuration in this priority order:
1. Environment variables (highest priority)
2. `.env` file in this directory
3. Default hardcoded values (lowest priority)

For production deployments, use `scripts/production/deploy.sh` which automatically creates a ConfigMap from `.env.production`.