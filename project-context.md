PROJECT CONTEXT: Hybrid Deterministic-ML Network Controller on Kubernetes

1. High-Level Project Goal

The objective is to build a hybrid deterministic-ML network controller in a Kubernetes cluster using the Cilium CNI.

"Hard Determinism": Guarantee low latency (<2ms) and zero packet loss for "Critical" applications using passive eBPF priority queuing.

"ML-Optimized": Dynamically maximize the bandwidth of "Best-Effort" applications without impacting critical traffic, using an active control loop.

2. The Test Environment: "Robot Factory" Simulation

We simulate a factory floor with 4 distinct applications deployed via manifests/robot-factory-application.yaml:

Critical (Hard Determinism):

robot-control (UDP iperf3 server, port 5201): Real-time control signals. Must have < 2ms jitter & 0% loss.

safety-scanner (TCP iperf3 server, port 5202): High-bandwidth safety data.

Best-Effort (ML-Optimized):

telemetry-upload (TCP iperf3 server, port 80): The "Noisy Neighbor". Simulates massive log uploads. Target for throttling.

erp-dashboard (TCP nginx server, port 80): Standard background web traffic.

3. Infrastructure & Constraints

Platform: 3-node Kubeadm cluster (1 master, 2 workers).

CNI: Cilium v1.18.3 with:

kubeProxyReplacement=true

bandwidthManager.enabled=true (Critical for eBPF QoS).

endpointRoutes.enabled=true.

Observability: Prometheus scraping Cilium Hubble Relay.

4. CORE TECHNICAL CHALLENGE & SOLUTION (The "Workaround")

The Problem: We cannot patch CiliumNetworkPolicy bandwidth limits directly because Cilium v1.18.3 throws an unknown field error for spec.egress.bandwidth.

The Solution (Workaround B):
We control bandwidth by patching the Kubernetes Deployment Annotations.

Mechanism: The ML Controller patches kubernetes.io/egress-bandwidth: "50M" on the telemetry-upload deployment.

Result: Cilium Bandwidth Manager detects this annotation change and updates the eBPF maps in real-time without restarting the pod.

5. METRICS & DATA PIPELINE (L4 Only)

Constraint: We strictly use L4 Flow Metrics (hubble_flow_latency_seconds_bucket) because L7 HTTP metrics introduced too much overhead.

Jitter Calculation: We calculate IQR (Interquartile Range) from the histogram:

Jitter = Q3 (75th pct) - Q1 (25th pct)

Query: histogram_quantile(0.75, rate(...)) - histogram_quantile(0.25, rate(...))

Latency: We monitor P95 latency.

Query: histogram_quantile(0.95, rate(...))

6. COMPONENT REFERENCE

manifests/robot-factory-application.yaml: Deploys all 4 apps (iperf3 servers).

manifests/best-effort-policy.yaml: A simple "allow" policy acting as a selector hook.

scripts/ml_controller.py: The Python Controller.

Polls Prometheus for L4 Jitter.

Implements Asymmetric Proportional Control (Cut fast, raise slow).

Patches kubernetes.io/egress-bandwidth on the target deployment.

manifests/ml_controller_deployment.yaml: Deploys the python script.

manifests/ml_controller_rbac.yaml: Grants permissions to patch deployments.

7. CURRENT STATUS

Passive Protection: PROVEN. robot-control (UDP) maintains 0% loss during congestion due to Cilium's implicit priority queuing.

Active Control: PROVEN. The controller successfully throttles telemetry-upload bandwidth via annotation patching when high jitter is detected (simulated).

Next Task: Refine the ml_controller.py to use the L4 Jitter (IQR) logic effectively with real Prometheus data.