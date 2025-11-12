# Building ML Controller Image with containerd

This guide explains how to build and push the ML controller image using **containerd** and **nerdctl** instead of Docker.

## Prerequisites

- `nerdctl` installed (containerd CLI)
- Access to a container registry (e.g., Docker Hub, private registry)

## Build Steps

### Option 1: Using `nerdctl` (Recommended for containerd)

1. **Build the image:**
```bash
nerdctl build -t fustli/ml-controller:latest \
  -f docker/ml-controller/Dockerfile \
  docker/ml-controller
```

2. **Tag for your registry** (if not Docker Hub):
```bash
# For private registry
nerdctl tag fustli/ml-controller:latest \
  registry.example.com/fustli/ml-controller:latest
```

3. **Push to registry:**
```bash
# Docker Hub
nerdctl push fustli/ml-controller:latest

# Private registry
nerdctl push registry.example.com/fustli/ml-controller:latest
```

### Option 2: Using `ctr` (containerd native CLI)

If you prefer the lower-level containerd client:

```bash
# Build using buildkit (requires buildkit plugin)
ctr images build --ref fustli/ml-controller:latest \
  -f docker/ml-controller/Dockerfile \
  docker/ml-controller
```

### Option 3: Using `buildctl` (BuildKit directly)

For advanced users with buildkit installed:

```bash
buildctl build --frontend dockerfile.v0 \
  --local context=docker/ml-controller \
  --local dockerfile=docker/ml-controller \
  --output type=image,name=fustli/ml-controller:latest,push=true
```

## Verify the Image

```bash
# List images
nerdctl images | grep ml-controller

# Inspect image
nerdctl inspect fustli/ml-controller:latest

# Test locally (optional)
nerdctl run --rm fustli/ml-controller:latest --help
```

## Kubernetes Deployment

Once pushed to your registry, the image is ready to use in the deployment:

```bash
kubectl apply -f manifests/ml_controller_rbac.yaml
kubectl apply -f manifests/ml-controller-configmap.yaml
kubectl apply -f manifests/ml-controller.yaml
```

## Image Specification

- **Base image:** `python:3.11-slim`
- **Non-root user:** `controller` (UID 1000) for security
- **Dependencies:** kubernetes, prometheus-api-client
- **Entry point:** `python /app/ml_controller.py`

## Troubleshooting

### Issue: `nerdctl` command not found
- Install nerdctl: https://github.com/containerd/nerdctl/releases

### Issue: Push fails with authentication error
```bash
nerdctl login registry.example.com
# Enter credentials when prompted
nerdctl push registry.example.com/fustli/ml-controller:latest
```

### Issue: Image size too large
- The slim base is already optimized; if needed, use `python:3.11-alpine` instead

## Security Notes

- Image runs as non-root user (`controller`)
- Uses minimal base image to reduce attack surface
- All pip packages installed without cache to reduce layers
