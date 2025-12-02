# Building Flow Manager Image with containerd

This guide explains how to build and push the Flow manager image using **containerd** and **nerdctl** instead of Docker.

## Prerequisites

- `nerdctl` installed (containerd CLI)
- Access to a container registry (e.g., Docker Hub, private registry)

## Build Steps

### Option 1: Using `nerdctl` (Recommended for containerd)

1. **Build the image:**
```bash
nerdctl build -t fustli/flow-manager:latest \
  -f docker/flow-manager/Dockerfile \
  docker/flow-manager
```

2. **Tag for your registry** (if not Docker Hub):
```bash
# For private registry
nerdctl tag fustli/flow-manager:latest \
  registry.example.com/fustli/flow-manager:latest
```

3. **Push to registry:**
```bash
# Docker Hub
nerdctl push fustli/flow-manager:latest

# Private registry
nerdctl push registry.example.com/fustli/flow-manager:latest
```

### Option 2: Using `ctr` (containerd native CLI)

If you prefer the lower-level containerd client:

```bash
# Build using buildkit (requires buildkit plugin)
ctr images build --ref fustli/flow-manager:latest \
  -f docker/flow-manager/Dockerfile \
  docker/flow-manager
```

### Option 3: Using `buildctl` (BuildKit directly)

For advanced users with buildkit installed:

```bash
buildctl build --frontend dockerfile.v0 \
  --local context=docker/flow-manager \
  --local dockerfile=docker/flow-manager \
  --output type=image,name=fustli/flow-manager:latest,push=true
```

## Verify the Image

```bash
# List images
nerdctl images | grep flow-manager

# Inspect image
nerdctl inspect fustli/flow-manager:latest

# Test locally (optional)
nerdctl run --rm fustli/flow-manager:latest --help
```

## Kubernetes Deployment

Once pushed to your registry, the image is ready to use in the deployment:

```bash
kubectl apply -f manifests/flow_manager_rbac.yaml
kubectl apply -f manifests/flow-manager-configmap.yaml
kubectl apply -f manifests/flow-manager.yaml
```

## Image Specification

- **Base image:** `python:3.11-slim`
- **Non-root user:** `controller` (UID 1000) for security
- **Dependencies:** kubernetes, prometheus-api-client
- **Entry point:** `python /app/flow_manager.py`

## Troubleshooting

### Issue: `nerdctl` command not found
- Install nerdctl: https://github.com/containerd/nerdctl/releases

### Issue: Push fails with authentication error
```bash
nerdctl login registry.example.com
# Enter credentials when prompted
nerdctl push registry.example.com/fustli/flow-manager:latest
```

### Issue: Image size too large
- The slim base is already optimized; if needed, use `python:3.11-alpine` instead

## Security Notes

- Image runs as non-root user (`controller`)
- Uses minimal base image to reduce attack surface
- All pip packages installed without cache to reduce layers
