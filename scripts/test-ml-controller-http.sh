#!/bin/bash
# HTTP-based Traffic Generator for ML Controller Testing
# Demonstrates internal pod-to-pod networking and bandwidth throttling

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   ML Controller Testing - HTTP Internal Networking Demo       ║${NC}"
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo ""

# Check if applications are deployed
echo -e "${YELLOW}[Step 1] Checking application deployments...${NC}"
kubectl get deployment robot-factory-deployment 2>/dev/null || {
    echo -e "${RED}✗ robot-factory-deployment not found!${NC}"
    echo -e "${YELLOW}  Deploying HTTP applications...${NC}"
    kubectl apply -f k8s/applications/http-traffic-generator.yaml
    echo -e "${YELLOW}  Waiting for deployments...${NC}"
    sleep 10
}

kubectl get deployment telemetry-upload-deployment 2>/dev/null || {
    echo -e "${YELLOW}  Telemetry upload deployment exists (from robot-factory-application.yaml)${NC}"
}

# Wait for pods
echo -e "${GREEN}✓ Waiting for pods to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=robot-factory --timeout=60s 2>/dev/null || echo "  (still starting...)"
kubectl wait --for=condition=ready pod -l app=telemetry-upload --timeout=60s 2>/dev/null || echo "  (still starting...)"

# Get pod info
ROBOT_POD=$(kubectl get pod -l app=robot-factory -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
ROBOT_IP=$(kubectl get pod -l app=robot-factory -o jsonpath='{.items[0].status.podIP}' 2>/dev/null)
TELEMETRY_POD=$(kubectl get pod -l app=telemetry-upload -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
TELEMETRY_IP=$(kubectl get pod -l app=telemetry-upload -o jsonpath='{.items[0].status.podIP}' 2>/dev/null)
CONTROLLER_POD=$(kubectl get pod -n kube-system -l app=ml-controller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

echo -e "${GREEN}✓ Application Status:${NC}"
echo -e "  ${BLUE}Robot Factory:${NC}     ${ROBOT_POD} (${ROBOT_IP})"
echo -e "  ${BLUE}Telemetry Upload:${NC}  ${TELEMETRY_POD} (${TELEMETRY_IP})"
echo -e "  ${BLUE}ML Controller:${NC}     ${CONTROLLER_POD}"
echo ""

# Check L7 policies
echo -e "${YELLOW}[Step 2] Checking Cilium L7 HTTP visibility policies...${NC}"
if kubectl get cnp robot-factory-l7-visibility 2>/dev/null >/dev/null; then
    echo -e "${GREEN}✓ L7 visibility policy exists${NC}"
else
    echo -e "${YELLOW}  Applying L7 visibility policies...${NC}"
    kubectl apply -f k8s/policies/robot-factory-l7-policy.yaml
    echo -e "${GREEN}✓ L7 policies applied - waiting for Cilium to process...${NC}"
    sleep 5
fi

# Check current bandwidth annotation
echo -e "${YELLOW}[Step 3] Current telemetry-upload bandwidth limit:${NC}"
CURRENT_BW=$(kubectl get deployment telemetry-upload-deployment -o jsonpath='{.metadata.annotations.kubernetes\.io/egress-bandwidth}' 2>/dev/null || echo "not set")
echo -e "  ${CYAN}Current limit: ${CURRENT_BW}${NC}"
echo ""

# Show ML controller status
echo -e "${YELLOW}[Step 4] ML Controller Status:${NC}"
kubectl logs -n kube-system $CONTROLLER_POD --tail=3 2>/dev/null || echo "  (controller starting...)"
echo ""

echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Starting Traffic Generation Tests                           ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Phase 1: Baseline - Only critical traffic
echo -e "${BLUE}[Phase 1] BASELINE - Critical traffic only${NC}"
echo -e "  Testing robot-factory HTTP latency without interference..."
echo ""

kubectl run http-test-baseline --rm -i --restart=Never --image=curlimages/curl:latest -- \
  sh -c "for i in \$(seq 1 20); do time curl -s http://robot-factory-svc/api/status > /dev/null; done" &
BASELINE_PID=$!

sleep 3
wait $BASELINE_PID 2>/dev/null
echo ""

# Phase 2: Add background noise (telemetry)
echo -e "${MAGENTA}[Phase 2] NOISE INJECTION - Adding heavy telemetry traffic${NC}"
echo -e "  Generating 100 Mbps telemetry upload traffic (best-effort)..."
echo -e "  ${YELLOW}⚠ This should increase robot-factory latency${NC}"
echo ""

# Start heavy TCP traffic to telemetry (iperf3)
kubectl run telemetry-noise-generator --rm -i --restart=Never --image=networkstatic/iperf3 -- \
  -c telemetry-upload-svc -b 100M -t 60 -p 80 &
NOISE_PID=$!

sleep 2

# Monitor robot-factory latency during noise
echo -e "${YELLOW}  Monitoring robot-factory latency during noise injection...${NC}"
kubectl run http-test-with-noise --rm -i --restart=Never --image=curlimages/curl:latest -- \
  sh -c "for i in \$(seq 1 20); do time curl -s http://robot-factory-svc/api/robot/position > /dev/null; sleep 0.5; done" &
NOISE_TEST_PID=$!

sleep 5

# Check ML controller reactions
echo ""
echo -e "${CYAN}[Monitoring] ML Controller Response:${NC}"
kubectl logs -n kube-system $CONTROLLER_POD --tail=10 2>/dev/null | grep -E "Throttling|Bandwidth|Jitter|Latency" || echo "  (checking metrics...)"

sleep 10

# Check if bandwidth was throttled
NEW_BW=$(kubectl get deployment telemetry-upload-deployment -o jsonpath='{.metadata.annotations.kubernetes\.io/egress-bandwidth}' 2>/dev/null || echo "not set")
echo ""
echo -e "${CYAN}[Status Check] Bandwidth Annotation:${NC}"
echo -e "  Before: ${CURRENT_BW}"
echo -e "  After:  ${NEW_BW}"

if [ "$NEW_BW" != "$CURRENT_BW" ] && [ "$NEW_BW" != "not set" ]; then
    echo -e "${GREEN}  ✓ ML Controller is THROTTLING telemetry traffic!${NC}"
else
    echo -e "${YELLOW}  ⚠ No throttling detected yet (controller may need more time)${NC}"
fi

echo ""
echo -e "${CYAN}[Phase 3] VALIDATION - Testing robot-factory latency after throttling${NC}"
kubectl run http-test-throttled --rm -i --restart=Never --image=curlimages/curl:latest -- \
  sh -c "for i in \$(seq 1 20); do time curl -s http://robot-factory-svc/api/robot/health > /dev/null; done" &
THROTTLED_PID=$!

# Wait for all tests
wait $NOISE_PID 2>/dev/null
wait $NOISE_TEST_PID 2>/dev/null
wait $THROTTLED_PID 2>/dev/null

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Test Complete - Review Results                              ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Show final controller status
echo -e "${GREEN}ML Controller Final Status:${NC}"
kubectl logs -n kube-system $CONTROLLER_POD --tail=15 2>/dev/null || echo "  (logs unavailable)"

echo ""
echo -e "${BLUE}═══ Next Steps ═══${NC}"
echo -e "1. Check Grafana dashboard: ${CYAN}http://localhost:3000${NC}"
echo -e "2. View Hubble HTTP metrics:"
echo -e "   ${CYAN}curl -s http://172.16.0.59:9965/metrics | grep hubble_http${NC}"
echo -e "3. Monitor controller logs continuously:"
echo -e "   ${CYAN}kubectl logs -n kube-system -l app=ml-controller -f${NC}"
echo -e "4. Check telemetry bandwidth annotation:"
echo -e "   ${CYAN}kubectl get deployment telemetry-upload-deployment -o yaml | grep bandwidth${NC}"
echo ""
echo -e "${YELLOW}Expected Behavior:${NC}"
echo -e "  • ${GREEN}Phase 1:${NC} Low latency (baseline)"
echo -e "  • ${RED}Phase 2:${NC} Increased latency (congestion from telemetry)"
echo -e "  • ${GREEN}Phase 3:${NC} Latency returns to normal (controller throttled telemetry)"
echo ""
