#!/bin/bash
set -e

# Production Deployment Script for K8s Deterministic Networking
# Deploys the ML Controller with proper configuration management

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${PROJECT_ROOT}/config"
K8S_DIR="${PROJECT_ROOT}/k8s"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    if [[ ! -f "${CONFIG_DIR}/.env.production" ]]; then
        log_error "Production configuration file not found: ${CONFIG_DIR}/.env.production"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Deploy infrastructure components
deploy_infrastructure() {
    log_info "Deploying infrastructure components..."
    
    kubectl apply -f "${K8S_DIR}/infrastructure/"
    
    log_success "Infrastructure components deployed"
}

# Deploy application
deploy_application() {
    log_info "Deploying ML Controller..."
    
    # Create configmap from production config
    kubectl create configmap ml-controller-config \
        --from-env-file="${CONFIG_DIR}/.env.production" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy the controller
    kubectl apply -f "${K8S_DIR}/applications/ml-controller.yaml"
    
    log_success "ML Controller deployed"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Wait for deployment to be ready
    kubectl rollout status deployment/ml-controller --timeout=300s
    
    # Check if pods are running
    RUNNING_PODS=$(kubectl get pods -l app=ml-controller --field-selector=status.phase=Running --no-headers | wc -l)
    
    if [[ $RUNNING_PODS -gt 0 ]]; then
        log_success "ML Controller is running successfully"
    else
        log_error "ML Controller deployment verification failed"
        kubectl get pods -l app=ml-controller
        exit 1
    fi
}

# Main deployment function
main() {
    log_info "Starting production deployment..."
    
    check_prerequisites
    deploy_infrastructure
    deploy_application
    verify_deployment
    
    log_success "Production deployment completed successfully!"
    log_info "Monitor the controller with: kubectl logs -f deployment/ml-controller"
}

# Show usage if --help is provided
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Production Deployment Script for K8s Deterministic Networking"
    echo ""
    echo "Usage: $0"
    echo ""
    echo "This script deploys the ML Controller to a production Kubernetes cluster."
    echo "Ensure you have:"
    echo "  - kubectl configured for your target cluster"
    echo "  - Production configuration in config/.env.production"
    echo "  - Appropriate cluster permissions"
    exit 0
fi

main "$@"