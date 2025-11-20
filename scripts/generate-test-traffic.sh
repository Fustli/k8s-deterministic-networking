#!/bin/bash
# Traffic Generator for Testing Deterministic Networking
# Generates realistic traffic patterns for different service types

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Deterministic Networking Traffic Generator ===${NC}"
echo -e "${BLUE}Testing QoS for: Robot Control, Safety Scanner, Telemetry Upload${NC}\n"

# Wait for pods to be ready
echo -e "${YELLOW}Waiting for application pods to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=robot-control --timeout=60s 2>/dev/null || echo "Robot control not ready"
kubectl wait --for=condition=ready pod -l app=safety-scanner --timeout=60s 2>/dev/null || echo "Safety scanner not ready"
kubectl wait --for=condition=ready pod -l app=telemetry-upload --timeout=60s 2>/dev/null || echo "Telemetry not ready"
kubectl wait --for=condition=ready pod -l app=erp-dashboard --timeout=60s 2>/dev/null || echo "ERP not ready"

# Get pod information
ROBOT_POD=$(kubectl get pod -l app=robot-control -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
SAFETY_POD=$(kubectl get pod -l app=safety-scanner -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
TELEMETRY_POD=$(kubectl get pod -l app=telemetry-upload -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

echo -e "${GREEN}✓ Pods ready:${NC}"
echo -e "  Robot Control: ${ROBOT_POD}"
echo -e "  Safety Scanner: ${SAFETY_POD}"
echo -e "  Telemetry Upload: ${TELEMETRY_POD}"
echo ""

# Test 1: Robot Control - Low latency UDP traffic
echo -e "${BLUE}[Test 1] Robot Control - Low-latency UDP (Critical QoS)${NC}"
echo -e "  - Protocol: UDP"
echo -e "  - Bandwidth: 1 Mbps (low)"
echo -e "  - Pattern: Continuous, low-jitter"
echo -e "  - Duration: 30 seconds"

kubectl run iperf-robot-test --rm -i --restart=Never --image=networkstatic/iperf3 -- \
  -c robot-control-svc -u -b 1M -t 30 -p 5201 &
TEST1_PID=$!

sleep 5

# Test 2: Safety Scanner - High bandwidth TCP
echo -e "\n${BLUE}[Test 2] Safety Scanner - High-bandwidth TCP (Critical QoS)${NC}"
echo -e "  - Protocol: TCP"
echo -e "  - Bandwidth: 50 Mbps (high, stable)"
echo -e "  - Pattern: Continuous scan data"
echo -e "  - Duration: 30 seconds"

kubectl run iperf-safety-test --rm -i --restart=Never --image=networkstatic/iperf3 -- \
  -c safety-scanner-svc -b 50M -t 30 -p 5202 &
TEST2_PID=$!

sleep 5

# Test 3: Telemetry Upload - Best effort, bursty
echo -e "\n${BLUE}[Test 3] Telemetry Upload - Best-effort traffic (Background)${NC}"
echo -e "  - Protocol: TCP"
echo -e "  - Bandwidth: 100 Mbps (unlimited, noisy)"
echo -e "  - Pattern: Bursty, background traffic"
echo -e "  - Duration: 60 seconds"

kubectl run iperf-telemetry-test --rm -i --restart=Never --image=networkstatic/iperf3 -- \
  -c telemetry-upload-svc -b 100M -t 60 -p 80 &
TEST3_PID=$!

echo -e "\n${YELLOW}Traffic generation in progress...${NC}"
echo -e "${YELLOW}Monitor in Grafana: http://localhost:3000${NC}"
echo -e "${YELLOW}Check metrics:${NC}"
echo -e "  - Latency: Should remain low for Robot Control"
echo -e "  - Jitter: Should be minimal for critical services"
echo -e "  - Bandwidth: ML Controller should limit Telemetry when needed"

# Wait for tests to complete
wait $TEST1_PID 2>/dev/null
wait $TEST2_PID 2>/dev/null  
wait $TEST3_PID 2>/dev/null

echo -e "\n${GREEN}=== Traffic Tests Complete ===${NC}"
echo -e "${GREEN}Check Grafana dashboard for QoS metrics:${NC}"
echo -e "  1. Inter-Node Latency"
echo -e "  2. Network Jitter (should be low)"
echo -e "  3. Flow Processing Rate"
echo -e "  4. Packet Drops (should be minimal for critical services)"
echo -e "\n${BLUE}To run continuously: watch -n 60 $0${NC}"
