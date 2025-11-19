"""
End-to-End Tests for K8s Deterministic Networking

Tests complete system scenarios from traffic generation to bandwidth control.
"""

import pytest
import sys
import os
from pathlib import Path
import subprocess
import time
import json
import random
from datetime import datetime

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TrafficGenerator:
    """Generate various traffic patterns for testing"""
    
    @staticmethod
    def run_kubectl(cmd, namespace="default"):
        """Run kubectl command"""
        full_cmd = f"kubectl {cmd}"
        if namespace != "default" and "-n" not in cmd:
            full_cmd = f"kubectl -n {namespace} {cmd}"
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode
    
    @staticmethod
    def generate_http_traffic(duration_seconds=30, requests_per_second=10):
        """Generate HTTP traffic to test bandwidth control"""
        # Use existing HTTP client pods to generate traffic
        output, code = TrafficGenerator.run_kubectl("get pods -l app=http-client -o jsonpath='{.items[0].metadata.name}'")
        if code != 0:
            raise Exception("No HTTP client pods found")
        
        http_pod = output
        
        # Generate traffic  
        cmd = f"exec {http_pod} -- bash -c 'for i in {{1..{duration_seconds}}}; do for j in {{1..{requests_per_second}}}; do curl -s http://telemetry-upload-svc/ >/dev/null & done; sleep 1; done; wait'"
        print(f"Generating HTTP traffic for {duration_seconds}s at {requests_per_second} req/s...")
        
        output, code = TrafficGenerator.run_kubectl(cmd)
        return code == 0
    
    @staticmethod
    def generate_burst_traffic():
        """Generate burst traffic to simulate congestion"""
        # Use burst traffic generator CronJob
        output, code = TrafficGenerator.run_kubectl("create job burst-test --from=cronjob/burst-traffic-generator")
        if code != 0:
            print(f"Could not create burst job: {output}")
            return False
        
        print("Burst traffic job created")
        return True
    
    @staticmethod 
    def get_network_metrics():
        """Get current network metrics"""
        # Get bandwidth from deployment
        bandwidth_output, _ = TrafficGenerator.run_kubectl('get deployment telemetry-upload-deployment -o jsonpath="{.spec.template.metadata.annotations.kubernetes\\.io/egress-bandwidth}"')
        
        # Get controller logs for jitter
        logs_output, _ = TrafficGenerator.run_kubectl("logs deployment/ml-controller --tail=5", "kube-system")
        
        jitter = None
        for line in logs_output.split('\n'):
            if "Current jitter:" in line:
                try:
                    jitter = float(line.split("Current jitter: ")[1].split("ms")[0])
                except:
                    pass
        
        return {
            'bandwidth': bandwidth_output,
            'jitter': jitter,
            'timestamp': datetime.now().isoformat()
        }


class TestRealWorldScenarios:
    """Test realistic network scenarios"""
    
    @pytest.fixture(scope="class")
    def system_ready(self):
        """Ensure entire system is ready"""
        traffic_gen = TrafficGenerator()
        
        # Check controller is ready
        output, code = traffic_gen.run_kubectl("get deployment ml-controller -o jsonpath='{.status.readyReplicas}'", "kube-system")
        if output != "1":
            pytest.skip("ML Controller not ready")
        
        # Check target deployment exists
        output, code = traffic_gen.run_kubectl("get deployment telemetry-upload-deployment")
        if code != 0:
            pytest.skip("Target deployment not found")
        
        # Check traffic clients exist
        output, code = traffic_gen.run_kubectl("get pods -l app=http-client")
        if "http-client" not in output:
            pytest.skip("Traffic clients not available")
        
        return True
    
    @pytest.mark.slow
    def test_normal_operations_scenario(self, system_ready):
        """Test normal low-traffic scenario (bandwidth should increase)"""
        traffic_gen = TrafficGenerator()
        
        print("\nTesting Normal Operations Scenario")
        print("Expected: Low jitter → Bandwidth increases over time")
        
        # Record initial state
        initial_metrics = traffic_gen.get_network_metrics()
        print(f"Initial: {initial_metrics['bandwidth']}, jitter: {initial_metrics['jitter']}ms")
        
        # Wait for normal operations (no additional traffic)
        metrics_history = [initial_metrics]
        
        for i in range(6):  # 30 seconds total
            time.sleep(5)
            metrics = traffic_gen.get_network_metrics()
            metrics_history.append(metrics)
            print(f"  t+{(i+1)*5}s: {metrics['bandwidth']}, jitter: {metrics['jitter']}ms")
        
        # Analysis
        bandwidths = [int(m['bandwidth'].replace('M', '')) for m in metrics_history if m['bandwidth']]
        
        print(f"\nBandwidth progression: {bandwidths}")
        
        # In normal conditions, bandwidth should increase (unless at maximum)
        if bandwidths[-1] < 1000:  # Not at maximum
            assert bandwidths[-1] >= bandwidths[0], f"Bandwidth should increase in normal conditions: {bandwidths[0]} → {bandwidths[-1]}"
            print("[SUCCESS] Bandwidth increased as expected in normal conditions")
        else:
            print("[OK] Bandwidth at maximum - normal for healthy system")
    
    @pytest.mark.slow
    def test_traffic_burst_scenario(self, system_ready):
        """Test system response to traffic bursts"""
        traffic_gen = TrafficGenerator()
        
        print("\nTesting Traffic Burst Scenario")
        print("Expected: Traffic burst → Potential jitter increase → Bandwidth adjustment")
        
        # Record baseline
        baseline_metrics = traffic_gen.get_network_metrics()
        print(f"Baseline: {baseline_metrics['bandwidth']}, jitter: {baseline_metrics['jitter']}ms")
        
        # Generate burst traffic
        print("Generating burst traffic...")
        burst_success = traffic_gen.generate_burst_traffic()
        
        if not burst_success:
            pytest.skip("Could not generate burst traffic")
        
        # Monitor system response for 60 seconds
        metrics_history = [baseline_metrics]
        
        for i in range(12):  # 60 seconds total
            time.sleep(5)
            metrics = traffic_gen.get_network_metrics()
            metrics_history.append(metrics)
            
            status = "[BURST]" if i < 6 else "[RECOVERY]"
            print(f"  {status} t+{(i+1)*5}s: {metrics['bandwidth']}, jitter: {metrics['jitter']}ms")
        
        # Analysis
        bandwidths = [int(m['bandwidth'].replace('M', '')) for m in metrics_history if m['bandwidth']]
        jitters = [m['jitter'] for m in metrics_history if m['jitter'] is not None]
        
        print(f"\nBandwidth progression: {bandwidths}")
        print(f"Jitter progression: {jitters}")
        
        # System should adapt to traffic changes
        bandwidth_changed = len(set(bandwidths)) > 1
        assert bandwidth_changed, "System should respond to traffic changes"
        print("[SUCCESS] System responded to traffic burst with bandwidth adjustments")
    
    def test_controller_failure_recovery(self, system_ready):
        """Test system recovery after controller failure"""
        traffic_gen = TrafficGenerator()
        
        print("\nTesting Controller Failure Recovery")
        
        # Record initial state
        initial_metrics = traffic_gen.get_network_metrics()
        print(f"Pre-failure: {initial_metrics['bandwidth']}")
        
        # Simulate controller failure (delete pod)
        print("Simulating controller failure...")
        pod_output, _ = traffic_gen.run_kubectl("get pod -l app=ml-controller -o jsonpath='{.items[0].metadata.name}'", "kube-system")
        traffic_gen.run_kubectl(f"delete pod {pod_output}", "kube-system")
        
        # Wait for recovery
        print("Waiting for controller recovery...")
        recovery_timeout = 60  # 60 seconds
        recovered = False
        
        for i in range(recovery_timeout // 5):
            time.sleep(5)
            
            # Check if controller is back
            ready_output, code = traffic_gen.run_kubectl("get deployment ml-controller -o jsonpath='{.status.readyReplicas}'", "kube-system")
            
            if code == 0 and ready_output == "1":
                print(f"Controller recovered after {(i+1)*5} seconds")
                recovered = True
                break
            
            print(f"  Recovery check {i+1}: {'[OK]' if code == 0 else '[FAIL]'}")
        
        assert recovered, "Controller did not recover within timeout"
        
        # Wait for normal operations to resume
        time.sleep(15)
        
        # Verify functionality restored
        recovery_metrics = traffic_gen.get_network_metrics()
        print(f"Post-recovery: {recovery_metrics['bandwidth']}, jitter: {recovery_metrics['jitter']}ms")
        
        # Should be actively controlling bandwidth again
        assert recovery_metrics['jitter'] is not None, "Controller not reporting jitter after recovery"
        assert recovery_metrics['bandwidth'].endswith('M'), "Bandwidth annotation malformed after recovery"
        
        print("[SUCCESS] Controller successfully recovered and resumed operations")
    
    @pytest.mark.slow
    def test_sustained_load_scenario(self, system_ready):
        """Test system behavior under sustained load"""
        traffic_gen = TrafficGenerator()
        
        print("\nTesting Sustained Load Scenario")
        
        # Generate sustained HTTP traffic in background
        print("Starting sustained HTTP traffic...")
        
        # Use a more aggressive traffic pattern
        success = traffic_gen.generate_http_traffic(duration_seconds=60, requests_per_second=20)
        
        if not success:
            pytest.skip("Could not generate sustained traffic")
        
        # Monitor system for stability over longer period
        metrics_history = []
        stable_periods = 0
        
        for i in range(18):  # 90 seconds total
            time.sleep(5)
            metrics = traffic_gen.get_network_metrics()
            metrics_history.append(metrics)
            
            # Check for stability (jitter within reasonable bounds)
            if metrics['jitter'] and metrics['jitter'] <= 2.0:
                stable_periods += 1
            
            phase = "[SUSTAINED]" if i < 12 else "[ANALYSIS]"
            print(f"  {phase} t+{(i+1)*5}s: {metrics['bandwidth']}, jitter: {metrics['jitter']}ms")
        
        # Analysis
        bandwidths = [int(m['bandwidth'].replace('M', '')) for m in metrics_history if m['bandwidth']]
        jitters = [m['jitter'] for m in metrics_history if m['jitter'] is not None]
        
        print(f"\nStability analysis:")
        print(f"Bandwidth range: {min(bandwidths)} - {max(bandwidths)}M")
        print(f"Jitter range: {min(jitters):.2f} - {max(jitters):.2f}ms")
        print(f"Stable periods: {stable_periods}/{len(metrics_history)}")
        
        # System should maintain stability under sustained load
        avg_jitter = sum(jitters) / len(jitters)
        assert avg_jitter <= 3.0, f"Average jitter too high under sustained load: {avg_jitter:.2f}ms"
        
        # Should not oscillate wildly
        bandwidth_variance = max(bandwidths) - min(bandwidths)
        assert bandwidth_variance <= 200, f"Bandwidth oscillation too high: {bandwidth_variance}M"
        
        print("✅ System maintained stability under sustained load")
    
    def test_network_policy_enforcement(self, system_ready):
        """Test that network policies are properly enforced"""
        traffic_gen = TrafficGenerator()
        
        print("\n🔍 Testing Network Policy Enforcement")
        
        # Check that critical traffic has priority
        policies_output, _ = traffic_gen.run_kubectl("get ciliumnetworkpolicies -A")
        
        critical_policies = ["robot-control-policy", "safety-scanner-policy"]
        for policy in critical_policies:
            assert policy in policies_output, f"Critical policy missing: {policy}"
        
        # Check policy status
        policy_status, _ = traffic_gen.run_kubectl("get ciliumnetworkpolicies -A -o jsonpath='{range .items[*]}{.metadata.name}: {.status.state}{\"\\n\"}{end}'")
        
        for line in policy_status.split('\n'):
            if line.strip() and any(policy in line for policy in critical_policies):
                policy_name, status = line.split(': ')
                assert status == "True", f"Critical policy {policy_name} not active"
        
        print("✅ Network policies properly enforced")


class TestPerformanceCharacteristics:
    """Test system performance characteristics"""
    
    def test_control_loop_timing(self):
        """Test that control loop maintains consistent timing"""
        traffic_gen = TrafficGenerator()
        
        print("\n🔍 Testing Control Loop Timing")
        
        # Collect timestamps from logs
        timestamps = []
        
        for i in range(10):  # 50 seconds of monitoring
            time.sleep(5)
            logs_output, _ = traffic_gen.run_kubectl("logs deployment/ml-controller --tail=2", "kube-system")
            
            for line in logs_output.split('\n'):
                if "Updated bandwidth limit" in line or "Current jitter:" in line:
                    # Extract timestamp from log
                    if line.strip():
                        timestamp_str = line.split(' - ')[0]
                        timestamps.append(timestamp_str)
                        break
        
        print(f"Collected {len(timestamps)} control loop iterations")
        
        # Should see regular activity
        assert len(timestamps) >= 8, f"Too few control iterations observed: {len(timestamps)}"
        
        print("✅ Control loop maintains regular timing")
    
    def test_resource_utilization(self):
        """Test controller resource usage is reasonable"""
        traffic_gen = TrafficGenerator()
        
        print("\n🔍 Testing Resource Utilization")
        
        # Get controller pod resource usage (if metrics-server available)
        controller_pod, code = traffic_gen.run_kubectl("get pod -l app=ml-controller -o jsonpath='{.items[0].metadata.name}'", "kube-system")
        
        if code == 0:
            # Check resource limits are set
            resources_output, _ = traffic_gen.run_kubectl(f"get pod {controller_pod} -o jsonpath='{{.spec.containers[0].resources}}'", "kube-system")
            
            if resources_output:
                print(f"Controller resources: {resources_output}")
                assert "limits" in resources_output, "Controller should have resource limits"
            
            # Check controller is not restarting frequently
            restart_count, _ = traffic_gen.run_kubectl(f"get pod {controller_pod} -o jsonpath='{{.status.containerStatuses[0].restartCount}}'", "kube-system")
            
            restart_count = int(restart_count) if restart_count.isdigit() else 0
            assert restart_count <= 2, f"Controller restarting too frequently: {restart_count} restarts"
            
            print("✅ Controller resource utilization is reasonable")


if __name__ == "__main__":
    # Run e2e tests with more verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short", "-m", "not slow"])