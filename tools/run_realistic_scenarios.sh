#!/bin/bash
set -e

# Realistic Traffic Scenario Test Runner
# Deploys test infrastructure and runs comprehensive traffic scenarios

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${PROJECT_ROOT}/tools"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites for realistic scenarios..."
    
    if ! command -v kubectl >/dev/null 2>&1; then
        log_error "kubectl not found"
        exit 1
    fi
    
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "python3 not found"
        exit 1
    fi
    
    # Check if required Python packages are installed
    if ! python3 -c "import aiohttp, asyncio" >/dev/null 2>&1; then
        log_warning "Installing required Python packages..."
        pip3 install aiohttp asyncio
    fi
    
    log_success "Prerequisites check passed"
}

# Deploy test infrastructure
deploy_test_infrastructure() {
    log_info "Deploying test infrastructure..."
    
    # Deploy speedtest server for traffic generation
    kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: speedtest-server
  labels:
    app: speedtest-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: speedtest-server
  template:
    metadata:
      labels:
        app: speedtest-server
      annotations:
        kubernetes.io/egress-bandwidth: "100M"
    spec:
      containers:
      - name: speedtest-server
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
        # Simple HTTP server for testing
        command: ["/bin/sh"]
        args:
        - -c
        - |
          cat > /etc/nginx/conf.d/default.conf <<EOF2
          server {
              listen 80;
              location /api/process {
                  add_header Access-Control-Allow-Origin *;
                  add_header Access-Control-Allow-Methods "POST, GET, OPTIONS";
                  add_header Access-Control-Allow-Headers "Content-Type";
                  if (\$request_method = 'OPTIONS') {
                      return 204;
                  }
                  return 200 '{"status":"ok","timestamp":"$(date)","size":"\$content_length"}';
                  add_header Content-Type application/json;
              }
              location /health {
                  return 200 'OK';
                  add_header Content-Type text/plain;
              }
          }
          EOF2
          nginx -g 'daemon off;'
---
apiVersion: v1
kind: Service
metadata:
  name: speedtest-server
spec:
  selector:
    app: speedtest-server
  ports:
  - port: 8080
    targetPort: 80
  type: ClusterIP
EOF
    
    log_info "Waiting for speedtest server to be ready..."
    kubectl wait --for=condition=ready pod -l app=speedtest-server --timeout=60s
    
    log_success "Test infrastructure deployed"
}

# Run traffic scenarios
run_realistic_scenarios() {
    log_info "Starting realistic traffic scenario suite..."
    
    # Get speedtest server endpoint
    SPEEDTEST_URL="http://speedtest-server:8080"
    
    log_info "Target service: ${SPEEDTEST_URL}"
    log_info "Running comprehensive production scenarios..."
    
    # Run from inside a pod to ensure network access
    kubectl run realistic-traffic-test \
        --image=python:3.11-slim \
        --rm -i --tty \
        --restart=Never \
        --overrides='{
          "spec": {
            "containers": [{
              "name": "realistic-traffic-test",
              "image": "python:3.11-slim",
              "command": ["sh", "-c"],
              "args": ["pip install aiohttp && python3 /tmp/realistic_traffic_generator.py --target http://speedtest-server:8080"],
              "volumeMounts": [{
                "name": "script-volume",
                "mountPath": "/tmp"
              }]
            }],
            "volumes": [{
              "name": "script-volume",
              "configMap": {
                "name": "realistic-traffic-script"
              }
            }],
            "restartPolicy": "Never"
          }
        }' \
        --dry-run=client -o yaml | kubectl apply -f -
}

# Setup monitoring
setup_monitoring() {
    log_info "Setting up monitoring for realistic scenarios..."
    
    # Create ConfigMap with the traffic generator script
    kubectl create configmap realistic-traffic-script \
        --from-file=realistic_traffic_generator.py="${TOOLS_DIR}/realistic_traffic_generator.py" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Import Grafana dashboard
    if kubectl get pods -l app=grafana >/dev/null 2>&1; then
        log_info "Grafana detected - importing realistic scenarios dashboard..."
        
        # Create dashboard ConfigMap
        kubectl create configmap grafana-realistic-dashboard \
            --from-file="${PROJECT_ROOT}/k8s/infrastructure/grafana-realistic-scenarios-dashboard.json" \
            --dry-run=client -o yaml | kubectl apply -f -
        
        log_success "Dashboard imported - access via Grafana UI"
    else
        log_warning "Grafana not found - deploy monitoring stack first"
    fi
}

# Monitor scenarios in real-time
monitor_scenarios() {
    log_info "Monitoring realistic scenarios in real-time..."
    log_info "Press Ctrl+C to stop monitoring"
    
    while true; do
        echo ""
        log_info "=== Network Metrics ($(date)) ==="
        
        # Get current bandwidth
        CURRENT_BW=$(kubectl get deployment speedtest-server -o jsonpath='{.spec.template.metadata.annotations.kubernetes\.io/egress-bandwidth}' 2>/dev/null || echo "Unknown")
        echo "Current Bandwidth Limit: ${CURRENT_BW}"
        
        # Check if ML Controller is running
        if kubectl get pods -l app=ml-controller >/dev/null 2>&1; then
            echo "ML Controller Status: Running"
        else
            echo "ML Controller Status: Not Found"
        fi
        
        # Show recent pods
        echo ""
        echo "Active Test Pods:"
        kubectl get pods -l app=speedtest-server,app=realistic-traffic-test --no-headers 2>/dev/null || echo "No test pods running"
        
        sleep 10
    done
}

# Cleanup test infrastructure
cleanup() {
    log_info "Cleaning up test infrastructure..."
    
    kubectl delete deployment speedtest-server --ignore-not-found=true
    kubectl delete service speedtest-server --ignore-not-found=true
    kubectl delete configmap realistic-traffic-script --ignore-not-found=true
    kubectl delete pod realistic-traffic-test --ignore-not-found=true
    
    log_success "Cleanup completed"
}

# Main execution
main() {
    case "${1:-run}" in
        "setup")
            check_prerequisites
            deploy_test_infrastructure
            setup_monitoring
            log_success "Realistic scenario infrastructure ready!"
            log_info "Run './run_realistic_scenarios.sh run' to start traffic generation"
            ;;
        "run")
            check_prerequisites
            deploy_test_infrastructure
            setup_monitoring
            run_realistic_scenarios
            ;;
        "monitor")
            monitor_scenarios
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"--help"|"-h")
            echo "Realistic Traffic Scenario Test Runner"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  setup    - Deploy test infrastructure and monitoring"
            echo "  run      - Run complete realistic traffic scenario suite"
            echo "  monitor  - Monitor scenarios in real-time"
            echo "  cleanup  - Remove all test infrastructure"
            echo "  help     - Show this help message"
            echo ""
            echo "The script will generate realistic production traffic patterns"
            echo "and allow you to visualize the ML Controller's behavior in Grafana."
            ;;
        *)
            log_error "Unknown command: $1"
            log_info "Run '$0 help' for usage information"
            exit 1
            ;;
    esac
}

main "$@"