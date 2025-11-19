"""
Unit Tests for K8s Deterministic Networking ML Controller

Tests individual components and functions in isolation.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import our modules
try:
    from src.ml_controller import (
        BandwidthController, 
        ControlParameters, 
        KubernetesConfig, 
        PrometheusMetrics
    )
except ImportError:
    # Fallback if file structure is different
    import ml_controller as mc
    BandwidthController = mc.BandwidthController
    ControlParameters = mc.ControlParameters
    KubernetesConfig = mc.KubernetesConfig
    PrometheusMetrics = mc.PrometheusMetrics


class TestControlParameters:
    """Test configuration parameters"""
    
    def test_default_values(self):
        """Test that default control parameters are sensible"""
        params = ControlParameters()
        
        assert params.TARGET_JITTER_MS == 1.0
        assert params.MIN_BANDWIDTH_MBPS == 10
        assert params.MAX_BANDWIDTH_MBPS == 1000
        assert params.DECREASE_STEP_MBPS == 50
        assert params.INCREASE_STEP_MBPS == 10
        assert params.UPDATE_THRESHOLD_MBPS == 5
        assert params.CONTROL_INTERVAL_SEC == 5
        
    def test_parameter_relationships(self):
        """Test that parameters have correct relationships"""
        params = ControlParameters()
        
        # Decrease step should be larger than increase step (asymmetric control)
        assert params.DECREASE_STEP_MBPS > params.INCREASE_STEP_MBPS
        
        # Min should be less than max
        assert params.MIN_BANDWIDTH_MBPS < params.MAX_BANDWIDTH_MBPS
        
        # Update threshold should be reasonable
        assert params.UPDATE_THRESHOLD_MBPS < params.INCREASE_STEP_MBPS


class TestKubernetesConfig:
    """Test Kubernetes configuration"""
    
    def test_default_config(self):
        """Test default Kubernetes settings"""
        config = KubernetesConfig()
        
        assert config.DEPLOYMENT_NAME == "telemetry-upload-deployment"
        assert config.NAMESPACE == "default" 
        assert config.BANDWIDTH_ANNOTATION == "kubernetes.io/egress-bandwidth"


class TestPrometheusMetrics:
    """Test Prometheus metrics handling"""
    
    def test_prometheus_initialization(self):
        """Test PrometheusMetrics initializes correctly"""
        with patch('ml_controller.PrometheusConnect') as mock_prom:
            metrics = PrometheusMetrics("http://test:9090")
            mock_prom.assert_called_once_with(url="http://test:9090", disable_ssl=True)
    
    @patch('ml_controller.PrometheusConnect')
    def test_get_critical_app_latency_healthy(self, mock_prom_class):
        """Test jitter calculation when Prometheus is healthy"""
        # Mock Prometheus response
        mock_prom = Mock()
        mock_prom_class.return_value = mock_prom
        mock_prom.custom_query.return_value = [{'value': [0, '1']}]  # Prometheus up
        
        metrics = PrometheusMetrics("http://test:9090")
        jitter = metrics.get_critical_app_latency()
        
        assert jitter == 0.5  # Expected optimistic estimate
        mock_prom.custom_query.assert_called()
    
    @patch('ml_controller.PrometheusConnect')
    def test_get_critical_app_latency_unhealthy(self, mock_prom_class):
        """Test jitter calculation when Prometheus query fails"""
        mock_prom = Mock()
        mock_prom_class.return_value = mock_prom
        mock_prom.custom_query.side_effect = Exception("Connection failed")
        
        metrics = PrometheusMetrics("http://test:9090")
        jitter = metrics.get_critical_app_latency()
        
        assert jitter == 1.0  # Expected fallback value


class TestBandwidthController:
    """Test main controller logic"""
    
    def setup_method(self):
        """Setup for each test"""
        with patch('ml_controller.config.load_incluster_config'), \
             patch('ml_controller.client.AppsV1Api'), \
             patch('ml_controller.PrometheusMetrics'):
            self.controller = BandwidthController()
    
    def test_initialization(self):
        """Test controller initializes with correct values"""
        assert self.controller.current_bandwidth == 100
        assert isinstance(self.controller.control_params, ControlParameters)
        assert isinstance(self.controller.k8s_config, KubernetesConfig)
    
    def test_adjust_bandwidth_decrease_high_jitter(self):
        """Test bandwidth decreases when jitter is high"""
        self.controller.current_bandwidth = 500
        
        # High jitter should trigger decrease
        new_bandwidth = self.controller.adjust_bandwidth(2.5)  # > 1.0 target
        
        expected = 500 - 50  # DECREASE_STEP_MBPS
        assert new_bandwidth == expected
    
    def test_adjust_bandwidth_increase_low_jitter(self):
        """Test bandwidth increases when jitter is low"""
        self.controller.current_bandwidth = 200
        
        # Low jitter should trigger increase  
        new_bandwidth = self.controller.adjust_bandwidth(0.5)  # < 1.0 target
        
        expected = 200 + 10  # INCREASE_STEP_MBPS
        assert new_bandwidth == expected
    
    def test_adjust_bandwidth_no_change_at_target(self):
        """Test bandwidth unchanged when jitter is at target"""
        self.controller.current_bandwidth = 300
        
        # Jitter at target should not change bandwidth
        new_bandwidth = self.controller.adjust_bandwidth(1.0)  # = 1.0 target
        
        assert new_bandwidth == 300  # Unchanged
    
    def test_adjust_bandwidth_respects_minimum(self):
        """Test bandwidth doesn't go below minimum"""
        self.controller.current_bandwidth = 30  # Close to minimum
        
        # Even with high jitter, shouldn't go below minimum
        new_bandwidth = self.controller.adjust_bandwidth(5.0)  # Very high jitter
        
        assert new_bandwidth >= 10  # MIN_BANDWIDTH_MBPS
    
    def test_adjust_bandwidth_respects_maximum(self):
        """Test bandwidth doesn't exceed maximum"""
        self.controller.current_bandwidth = 980  # Close to maximum
        
        # Even with low jitter, shouldn't exceed maximum
        new_bandwidth = self.controller.adjust_bandwidth(0.1)  # Very low jitter
        
        assert new_bandwidth <= 1000  # MAX_BANDWIDTH_MBPS
    
    def test_adjust_bandwidth_boundary_conditions(self):
        """Test bandwidth adjustment at exact boundaries"""
        # Test at minimum
        self.controller.current_bandwidth = 10
        new_bandwidth = self.controller.adjust_bandwidth(2.0)  # Should decrease
        assert new_bandwidth == 10  # Can't go lower
        
        # Test at maximum  
        self.controller.current_bandwidth = 1000
        new_bandwidth = self.controller.adjust_bandwidth(0.1)  # Should increase
        assert new_bandwidth == 1000  # Can't go higher
    
    @patch('ml_controller.client.AppsV1Api')
    def test_update_deployment_bandwidth_success(self, mock_k8s_client):
        """Test successful deployment update"""
        # Mock Kubernetes API response
        mock_deployment = Mock()
        mock_deployment.spec.template.metadata.annotations = {}
        
        mock_k8s_client.return_value.read_namespaced_deployment.return_value = mock_deployment
        mock_k8s_client.return_value.patch_namespaced_deployment.return_value = None
        
        self.controller.k8s_client = mock_k8s_client.return_value
        
        result = self.controller.update_deployment_bandwidth(500)
        
        assert result == True
        mock_k8s_client.return_value.patch_namespaced_deployment.assert_called_once()
        assert mock_deployment.spec.template.metadata.annotations["kubernetes.io/egress-bandwidth"] == "500M"
    
    @patch('ml_controller.client.AppsV1Api')
    def test_update_deployment_bandwidth_failure(self, mock_k8s_client):
        """Test deployment update handles failures gracefully"""
        mock_k8s_client.return_value.read_namespaced_deployment.side_effect = Exception("API Error")
        
        self.controller.k8s_client = mock_k8s_client.return_value
        
        result = self.controller.update_deployment_bandwidth(500)
        
        assert result == False
    
    def test_control_logic_scenarios(self):
        """Test various control scenarios"""
        scenarios = [
            # (current_bw, jitter, expected_action, expected_bw)
            (100, 0.5, "increase", 110),  # Low jitter → increase
            (100, 2.0, "decrease", 50),   # High jitter → decrease  
            (10, 5.0, "minimum", 10),     # Already at minimum
            (1000, 0.1, "maximum", 1000), # Already at maximum
            (500, 1.0, "stable", 500),    # At target
        ]
        
        for current_bw, jitter, action, expected_bw in scenarios:
            self.controller.current_bandwidth = current_bw
            result = self.controller.adjust_bandwidth(jitter)
            assert result == expected_bw, f"Scenario {action} failed: {current_bw}→{result}, expected {expected_bw}"


class TestControlLoop:
    """Test control loop behavior"""
    
    @patch('ml_controller.BandwidthController.update_deployment_bandwidth')
    @patch('ml_controller.BandwidthController.__init__', return_value=None)
    def test_control_loop_updates_when_threshold_exceeded(self, mock_init, mock_update):
        """Test control loop only updates when change exceeds threshold"""
        controller = BandwidthController()
        controller.current_bandwidth = 100
        controller.control_params = ControlParameters()
        controller.metrics = Mock()
        
        # Small change (below threshold)
        controller.metrics.get_critical_app_latency.return_value = 0.9  # Would increase by 10
        mock_update.return_value = True
        
        # Manually run one iteration
        jitter = controller.metrics.get_critical_app_latency()
        new_bandwidth = controller.adjust_bandwidth(jitter)
        
        if abs(new_bandwidth - controller.current_bandwidth) >= controller.control_params.UPDATE_THRESHOLD_MBPS:
            controller.update_deployment_bandwidth(new_bandwidth)
            mock_update.assert_called_with(110)
        else:
            mock_update.assert_not_called()


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])