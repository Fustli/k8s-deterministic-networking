#!/bin/bash

# generate_traffic_patterns.sh - A script to generate iperf3 traffic with different patterns to test network controllers.

# This script is designed to be run from a pod within the Kubernetes cluster to
# generate load against a target service.

# --- Configuration (can be overridden by environment variables) ---

# The iperf3 server target. This should be the name of the Kubernetes service.
# The project context specifies the 'telemetry-upload' service as the noise source.
TARGET_SERVICE=${IPERF_TARGET_SERVICE:-"telemetry-upload"}

# The port the iperf3 server is listening on.
# The project context specifies TCP/80 for the 'telemetry-upload' service. Note: iperf3 on port 80 is unusual.
# Ensure an iperf3 server, not a web server, is listening on this port.
TARGET_PORT=${IPERF_TARGET_PORT:-"80"}

# Test duration and parameters for traffic patterns
STEP_DURATION_S=${STEP_DURATION_S:-"10"}
STEP_COUNT=${STEP_COUNT:-"10"}
STEP_INCREMENT_MBPS=${STEP_INCREMENT_MBPS:-"10"}
BURST_DURATION_S=${BURST_DURATION_S:-"5"}
BURST_BITRATE=${BURST_BITRATE:-"1G"}
RANDOM_TOTAL_DURATION_S=${RANDOM_TOTAL_DURATION_S:-"60"}
RANDOM_INTERVAL_S=${RANDOM_INTERVAL_S:-"5"}
RANDOM_MAX_MBPS=${RANDOM_MAX_MBPS:-"100"}


# --- Helper Functions ---
function run_iperf() {
    local bitrate=$1
    local duration=$2
    echo "--> Generating ${bitrate} load for ${duration}s..."
    # -c: client mode
    # -t: time in seconds
    # -b: target bitrate
    # -J: JSON output can be useful but is noisy for interactive use. Omitting for clarity.
    # -O 5: Omit the first 5 seconds from test results to skip TCP slow start.
    iperf3 -c "${TARGET_SERVICE}" -p "${TARGET_PORT}" -b "${bitrate}" -t "${duration}" -O 5
    if [ $? -ne 0 ]; then
        echo "Error: iperf3 command failed. Is an iperf3 server running at ${TARGET_SERVICE}:${TARGET_PORT}?" >&2
        # We don't exit here to allow random pattern to continue if one run fails.
        return 1
    fi
    return 0
}


# --- Pattern Definitions ---

function step_load() {
    echo "Starting Step Load pattern: 0 to $((${STEP_COUNT} * ${STEP_INCREMENT_MBPS}))Mbps..."
    for i in $(seq 1 ${STEP_COUNT}); do
        BITRATE=$((i * ${STEP_INCREMENT_MBPS}))
        run_iperf "${BITRATE}M" "${STEP_DURATION_S}"
    done
    echo "Step Load pattern complete."
}

function burst_load() {
    echo "Starting Burst Load pattern..."
    run_iperf "${BURST_BITRATE}" "${BURST_DURATION_S}"
    echo "Burst Load pattern complete."
}

function random_load() {
    echo "Starting Random Fluctuation pattern for ${RANDOM_TOTAL_DURATION_S} seconds..."
    END_TIME=$(($(date +%s) + ${RANDOM_TOTAL_DURATION_S}))
    while [ $(date +%s) -lt ${END_TIME} ]; do
        # Generate a random bitrate between 1M and RANDOM_MAX_MBPS.
        BITRATE=$(( (RANDOM % ${RANDOM_MAX_MBPS}) + 1 ))
        run_iperf "${BITRATE}M" "${RANDOM_INTERVAL_S}"
        # Sleep for a moment to create a small gap between intervals
        sleep 1
    done
    echo "Random Fluctuation pattern complete."
}

# --- Main ---
PATTERN=$1
if [ -z "$PATTERN" ]; then
    echo "Error: No pattern specified." >&2
    echo "Usage: $0 {step|burst|random}" >&2
    exit 1
fi

echo "Starting traffic generation..."
echo "Target Service: ${TARGET_SERVICE}:${TARGET_PORT}"
echo "Pattern: ${PATTERN}"
echo "---"

case "$PATTERN" in
    step)
        step_load
        ;;
    burst)
        burst_load
        ;;
    random)
        random_load
        ;;
    *)
        echo "Error: Unknown pattern '$PATTERN'." >&2
        echo "Available patterns: {step|burst|random}" >&2
        exit 1
        ;;
esac

echo "---"
echo "Traffic generation finished."
