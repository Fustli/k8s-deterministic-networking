#!/bin/bash
# Import/Update Flow Manager Dashboard into Grafana

DASHBOARD_JSON="/home/ubuntu/k8s-deterministic-networking/manifests/infrastructure/grafana-flow-manager-dashboard.json"
GRAFANA_URL="http://admin:admin123@localhost:3000"

echo "Importing Flow Manager Dashboard to Grafana..."
echo ""

# Check if port-forward is needed
if ! curl -s "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
    echo "Starting port-forward to Grafana..."
    kubectl port-forward -n monitoring svc/grafana 3000:3000 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3
    
    # Trap to kill port-forward on exit
    trap "kill $PF_PID 2>/dev/null" EXIT
fi

# Wait for Grafana to be ready
echo "Waiting for Grafana to be ready..."
for i in {1..30}; do
    if curl -s "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo "✅ Grafana is ready"
        break
    fi
    sleep 2
done

# Create the dashboard JSON payload
DASHBOARD_PAYLOAD=$(cat "$DASHBOARD_JSON" | jq '{dashboard: ., overwrite: true, folderId: 0}')

# Import the dashboard
echo ""
echo "Importing dashboard..."
RESPONSE=$(echo "$DASHBOARD_PAYLOAD" | curl -s -X POST \
    -H "Content-Type: application/json" \
    -d @- \
    "$GRAFANA_URL/api/dashboards/db")

# Check response
if echo "$RESPONSE" | grep -q '"status":"success"'; then
    DASHBOARD_URL=$(echo "$RESPONSE" | jq -r '.url')
    echo "✅ Dashboard imported successfully!"
    echo ""
    echo "📊 Dashboard URL: http://localhost:3000$DASHBOARD_URL"
    echo ""
    echo "Key updates:"
    echo "  • Robot Control Jitter: 0-1ms range (was 0-20ms)"
    echo "  • Thresholds: Yellow 0.15ms, Red 0.2ms"
    echo "  • 3 decimal precision for sub-millisecond accuracy"
else
    echo "❌ Failed to import dashboard"
    echo "Response: $RESPONSE"
    exit 1
fi
