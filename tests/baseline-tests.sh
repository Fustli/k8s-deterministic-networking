#!/bin/bash
echo "Starting Flannel baseline tests..."

# Apply test infrastructure
kubectl apply -f manifest/speedtest-server.yaml
sleep 10

# Run comprehensive client tests
kubectl apply -f manifest/speedtest-client-same-node.yaml

# Wait for completion and get results
sleep 35
kubectl logs job/speedtest-client-same-node > /results/flannel-baseline-$(date +%Y%m%d-%H%M).txt

echo "Baseline tests complete. Results saved to results/"
