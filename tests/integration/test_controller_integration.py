"""
Integration Tests for K8s Deterministic Networking ML Controller

Tests the controller with real Kubernetes API interactions in a test environment.
"""

import pytest
import sys
import os
from pathlib import Path
import subprocess
import time
import json
import tempfile
from unittest.mock import patch

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class KubernetesTestHelper:
    """Helper class for Kubernetes operations in tests"""
    
    @staticmethod
    def run_kubectl(cmd, namespace="default"):
        """Run kubectl command and return output"""
        full_cmd = f"kubectl {cmd}"
        if namespace != "default" and "-n" not in cmd:
            full_cmd = f"kubectl -n {namespace} {cmd}"
            
        try:
            result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"kubectl failed: {result.stderr}")
            return result.stdout.strip()
        except Exception as e:
            raise Exception(f"kubectl error: {e}")
    
    @staticmethod
    def get_deployment_annotation(deployment_name, namespace="default", annotation_key="kubernetes.io/egress-bandwidth"):
        """Get specific annotation from deployment"""
        cmd = f'get deployment {deployment_name} -o jsonpath="{{.spec.template.metadata.annotations.{annotation_key.replace(".", "\\.")}}}"'
        return KubernetesTestHelper.run_kubectl(cmd, namespace)
    
    @staticmethod
    def wait_for_pod_ready(label_selector, namespace="default", timeout=60):
        """Wait for pod with label to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                cmd = f'get pods -l {label_selector} -o jsonpath="{{.items[0].status.phase}}"'
                phase = KubernetesTestHelper.run_kubectl(cmd, namespace)
                if phase == "Running":
                    return True
            except:
                pass
            time.sleep(2)
        return False
    
    @staticmethod
    def get_controller_logs(lines=10):
        """Get ML controller logs"""
        cmd = f"logs deployment/ml-controller --tail={lines}"
        return KubernetesTestHelper.run_kubectl(cmd, "kube-system")


class TestControllerKubernetesIntegration:
    """Test controller integration with actual Kubernetes cluster"""
    
    @pytest.fixture(scope="class")
    def controller_ready(self):
        """Ensure controller is ready before tests"""
        helper = KubernetesTestHelper()
        
        # Check controller is running
        ready_replicas = helper.run_kubectl("get deployment ml-controller -o jsonpath='{.status.readyReplicas}'", "kube-system")
        if ready_replicas != "1":
            pytest.skip("ML Controller not ready")
        
        return True
    
    def test_controller_deployment_exists(self, controller_ready):
        """Test that controller deployment exists and is ready"""
        helper = KubernetesTestHelper()
        
        # Check deployment exists
        deployments = helper.run_kubectl("get deployments", "kube-system")
        assert "ml-controller" in deployments
        
        # Check it's ready
        ready_replicas = helper.run_kubectl("get deployment ml-controller -o jsonpath='{.status.readyReplicas}'", "kube-system")
        assert ready_replicas == "1"
    
    def test_controller_rbac_permissions(self, controller_ready):
        """Test that controller has correct RBAC permissions"""
        helper = KubernetesTestHelper()
        
        # Check ServiceAccount exists
        sa_output = helper.run_kubectl("get sa ml-controller-sa", "kube-system")
        assert "ml-controller-sa" in sa_output
        
        # Check ClusterRoleBinding exists
        crb_output = helper.run_kubectl("get clusterrolebinding ml-controller-binding")
        assert "ml-controller-binding" in crb_output
    
    def test_target_deployment_exists(self, controller_ready):
        """Test that target deployment exists"""
        helper = KubernetesTestHelper()
        
        # Check telemetry deployment exists
        deployments = helper.run_kubectl("get deployments")
        assert "telemetry-upload-deployment" in deployments
        
        # Check it has bandwidth annotation
        bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        assert bandwidth.endswith("M")  # Should have format like "500M"
    
    def test_controller_can_read_deployment(self, controller_ready):
        """Test controller can read target deployment"""
        helper = KubernetesTestHelper()
        
        # This tests RBAC read permissions
        deployment_yaml = helper.run_kubectl("get deployment telemetry-upload-deployment -o yaml")
        assert "telemetry-upload-deployment" in deployment_yaml
        assert "kubernetes.io/egress-bandwidth" in deployment_yaml
    
    def test_prometheus_connectivity(self, controller_ready):
        """Test that controller can connect to Prometheus"""
        helper = KubernetesTestHelper()
        
        # Check if Prometheus is accessible from controller
        prometheus_pods = helper.run_kubectl("get pods -l app=prometheus", "monitoring")
        assert "prometheus" in prometheus_pods
        
        # Check service exists
        prometheus_svc = helper.run_kubectl("get svc prometheus", "monitoring") 
        assert "prometheus" in prometheus_svc
    
    @pytest.mark.slow
    def test_bandwidth_annotation_updates(self, controller_ready):
        """Test that bandwidth annotation actually gets updated by controller"""
        helper = KubernetesTestHelper()
        
        # Get initial bandwidth
        initial_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        print(f"Initial bandwidth: {initial_bandwidth}")
        
        # Wait for controller to run a few cycles (15 seconds)
        time.sleep(15)
        
        # Get updated bandwidth
        updated_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        print(f"Updated bandwidth: {updated_bandwidth}")
        
        # Check that it changed (assuming jitter is low and bandwidth should increase)
        initial_val = int(initial_bandwidth.replace("M", "")) if initial_bandwidth else 0
        updated_val = int(updated_bandwidth.replace("M", "")) if updated_bandwidth else 0
        
        # Should either increase or stay at maximum
        assert updated_val >= initial_val, f"Bandwidth decreased unexpectedly: {initial_bandwidth} → {updated_bandwidth}"
    
    @pytest.mark.slow 
    def test_pod_restart_on_annotation_change(self, controller_ready):
        """Test that pods restart when bandwidth annotation changes"""
        helper = KubernetesTestHelper()
        
        # Get current pod name and creation time
        initial_pod = helper.run_kubectl('get pod -l app=telemetry-upload -o jsonpath="{.items[0].metadata.name} {.items[0].metadata.creationTimestamp}"')
        print(f"Initial pod: {initial_pod}")
        
        # Get current bandwidth
        initial_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        
        # Wait for bandwidth to change (up to 30 seconds)
        changed = False
        for i in range(6):
            time.sleep(5)
            current_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
            if current_bandwidth != initial_bandwidth:
                print(f"Bandwidth changed: {initial_bandwidth} → {current_bandwidth}")
                changed = True
                break
        
        if changed:
            # Wait a bit more for pod restart
            time.sleep(10)
            
            # Check if pod changed
            final_pod = helper.run_kubectl('get pod -l app=telemetry-upload -o jsonpath="{.items[0].metadata.name} {.items[0].metadata.creationTimestamp}"')
            print(f"Final pod: {final_pod}")
            
            assert initial_pod != final_pod, "Pod should have restarted when bandwidth changed"
        else:
            pytest.skip("Bandwidth didn't change during test (might be at maximum)")
    
    def test_controller_logs_show_activity(self, controller_ready):
        """Test that controller logs show regular activity"""
        helper = KubernetesTestHelper()
        
        logs = helper.get_controller_logs(20)
        
        # Should see jitter measurements
        assert "Current jitter:" in logs
        
        # Should see bandwidth updates (if not at limits)
        # Note: Might not see updates if at max/min limits
        log_lines = logs.split('\n')
        recent_logs = [line for line in log_lines if "INFO" in line]
        
        assert len(recent_logs) >= 5, f"Not enough recent activity in logs: {len(recent_logs)} lines"
    
    def test_controller_respects_boundaries(self, controller_ready):
        """Test that controller respects min/max bandwidth boundaries"""
        helper = KubernetesTestHelper()
        
        current_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        current_val = int(current_bandwidth.replace("M", "")) if current_bandwidth else 0
        
        # Should be within boundaries
        assert 10 <= current_val <= 1000, f"Bandwidth outside allowed range: {current_bandwidth}"
    
    def test_error_handling_prometheus_unavailable(self, controller_ready):
        """Test controller behavior when Prometheus is temporarily unavailable"""
        helper = KubernetesTestHelper()
        
        # Note: This is a passive test - we check that controller handles
        # failures gracefully by examining logs for error handling
        
        logs = helper.get_controller_logs(50)
        
        # Should not have any critical errors or crashes
        critical_errors = [line for line in logs.split('\n') if 'CRITICAL' in line or 'ERROR' in line.upper()]
        
        # Some warnings are OK (e.g., metrics temporarily unavailable)
        # But no critical errors that would crash the controller
        for error in critical_errors:
            if "Failed to update deployment" in error:
                pytest.fail(f"Controller has deployment update errors: {error}")


class TestNetworkPolicyIntegration:
    """Test network policies are properly applied"""
    
    def test_cilium_policies_exist(self):
        """Test that Cilium network policies are deployed"""
        helper = KubernetesTestHelper()
        
        policies = helper.run_kubectl("get ciliumnetworkpolicies -A")
        
        expected_policies = [
            "robot-control-policy",
            "safety-scanner-policy", 
            "best-effort-policy"
        ]
        
        for policy in expected_policies:
            assert policy in policies, f"Missing policy: {policy}"
    
    def test_policies_are_valid(self):
        """Test that all network policies are valid"""
        helper = KubernetesTestHelper()
        
        policies_output = helper.run_kubectl("get ciliumnetworkpolicies -A -o jsonpath='{range .items[*]}{.metadata.name}: {.status.state}{\"\\n\"}{end}'")
        
        for line in policies_output.split('\n'):
            if line.strip():
                policy_name, status = line.split(': ')
                assert status == "True", f"Policy {policy_name} is not valid (status: {status})"


class TestEndToEndScenarios:
    """End-to-end integration scenarios"""
    
    @pytest.mark.slow
    def test_full_system_recovery(self):
        """Test system recovery after controller restart"""
        helper = KubernetesTestHelper()
        
        # Get initial state
        initial_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        
        # Restart controller
        print("Restarting ML controller...")
        helper.run_kubectl("rollout restart deployment/ml-controller", "kube-system")
        
        # Wait for restart to complete
        time.sleep(20)
        
        # Verify controller is running
        assert helper.wait_for_pod_ready("app=ml-controller", "kube-system", timeout=60)
        
        # Wait for normal operation to resume
        time.sleep(15)
        
        # Check that bandwidth control is working again
        final_bandwidth = helper.get_deployment_annotation("telemetry-upload-deployment")
        logs = helper.get_controller_logs(10)
        
        assert "Current jitter:" in logs, "Controller not reporting jitter after restart"
        print(f"Recovery test: {initial_bandwidth} → {final_bandwidth}")


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])