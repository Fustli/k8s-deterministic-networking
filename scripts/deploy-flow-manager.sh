#!/bin/bash

#######################################################################
# Flow Manager Deployment Script
# Hybrid Deterministic-ML Network Controller for Kubernetes
#
# Usage: ./deploy-flow-manager.sh [command]
#   deploy     - Deploy/update the flow manager
#   undeploy   - Remove the flow manager
#   logs       - Watch flow manager logs
#   status     - Show current status
#   test       - Run traffic pattern test
#   grafana    - Port-forward Grafana
#######################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONTROLLER_DIR="${PROJECT_ROOT}/controller"
MANIFESTS_DIR="${PROJECT_ROOT}/manifests/control"
INFRA_DIR="${PROJECT_ROOT}/manifests/infrastructure"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster."
        exit 1
    fi
    
    log_success "Prerequisites OK"
}

deploy_flow_manager() {
    log_info "Deploying Flow Manager..."
    
    # Step 1: Create ConfigMap with flow_manager.py
    log_info "Creating ConfigMap with flow_manager.py..."
    kubectl create configmap flow-manager-script \
        --from-file=flow_manager.py="${CONTROLLER_DIR}/flow_manager.py" \
        -n kube-system \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Step 2: Deploy workload applications (if not already running)
    log_info "Ensuring workload applications are deployed..."
    kubectl apply -f "${PROJECT_ROOT}/manifests/applications/servers/workload-applications.yaml" || true
    kubectl apply -f "${PROJECT_ROOT}/manifests/applications/clients/best-effort-applications.yaml" || true
    kubectl apply -f "${PROJECT_ROOT}/manifests/applications/clients/traffic-generator.yaml" || true
    
    # Step 3: Deploy the Flow Manager
    log_info "Deploying Flow Manager controller..."
    kubectl apply -f "${MANIFESTS_DIR}/ml-controller.yaml"
    
    # Step 4: Wait for rollout
    log_info "Waiting for Flow Manager to be ready..."
    kubectl rollout status deployment/flow-manager -n kube-system --timeout=120s
    
    log_success "Flow Manager deployed successfully!"
    
    # Show status
    echo ""
    kubectl get pods -n kube-system -l app=flow-manager
}

undeploy_flow_manager() {
    log_info "Removing Flow Manager..."
    
    kubectl delete deployment flow-manager -n kube-system --ignore-not-found
    kubectl delete configmap flow-manager-script -n kube-system --ignore-not-found
    
    log_success "Flow Manager removed"
}

show_logs() {
    log_info "Streaming Flow Manager logs (Ctrl+C to stop)..."
    kubectl logs -n kube-system -l app=flow-manager -f --tail=100
}

show_status() {
    echo ""
    echo "=========================================="
    echo "       FLOW MANAGER STATUS"
    echo "=========================================="
    echo ""
    
    log_info "Flow Manager Pod:"
    kubectl get pods -n kube-system -l app=flow-manager -o wide
    echo ""
    
    log_info "Current Bandwidth Annotations:"
    echo "  telemetry-upload-deployment: $(kubectl get deployment telemetry-upload-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}' 2>/dev/null || echo 'Not Set')"
    echo "  erp-dashboard-deployment: $(kubectl get deployment erp-dashboard-deployment -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}' 2>/dev/null || echo 'Not Set')"
    echo ""
    
    log_info "Critical App Pods:"
    kubectl get pods -l priority=critical -o wide
    echo ""
    
    log_info "Best-Effort App Pods:"
    kubectl get pods -l priority=best-effort -o wide
    echo ""
    
    log_info "Recent Controller Logs:"
    kubectl logs -n kube-system -l app=flow-manager --tail=10 2>/dev/null || echo "  (no logs available)"
}

run_traffic_test() {
    log_info "Starting Traffic Pattern Test..."
    
    # Check if traffic_pattern_runner.py exists
    RUNNER="${PROJECT_ROOT}/scripts/traffic_pattern_runner.py"
    if [[ ! -f "$RUNNER" ]]; then
        log_error "traffic_pattern_runner.py not found at $RUNNER"
        exit 1
    fi
    
    # Run the test
    python3 "$RUNNER" --pattern full_test
}

port_forward_grafana() {
    log_info "Port-forwarding Grafana to localhost:3000..."
    log_info "Access at: http://localhost:3000 (admin/admin123)"
    log_info "Press Ctrl+C to stop"
    
    kubectl port-forward -n monitoring svc/grafana 3000:3000
}

import_dashboard() {
    log_info "Importing Grafana dashboard..."
    
    DASHBOARD_JSON="${INFRA_DIR}/grafana-flow-manager-dashboard.json"
    if [[ ! -f "$DASHBOARD_JSON" ]]; then
        log_error "Dashboard JSON not found: $DASHBOARD_JSON"
        exit 1
    fi
    
    # Create ConfigMap for dashboard provisioning
    kubectl create configmap grafana-flow-manager-dashboard \
        --from-file=flow-manager.json="$DASHBOARD_JSON" \
        -n monitoring \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "Dashboard ConfigMap created"
    log_info "Restart Grafana to load the dashboard, or import manually via UI"
}

usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy      Deploy/update the Flow Manager"
    echo "  undeploy    Remove the Flow Manager"
    echo "  logs        Watch Flow Manager logs"
    echo "  status      Show current status"
    echo "  test        Run traffic pattern validation test"
    echo "  grafana     Port-forward Grafana to localhost:3000"
    echo "  dashboard   Import Grafana dashboard"
    echo ""
}

# Main
case "${1:-}" in
    deploy)
        check_prerequisites
        deploy_flow_manager
        ;;
    undeploy)
        check_prerequisites
        undeploy_flow_manager
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    test)
        run_traffic_test
        ;;
    grafana)
        port_forward_grafana
        ;;
    dashboard)
        import_dashboard
        ;;
    *)
        usage
        exit 1
        ;;
esac
