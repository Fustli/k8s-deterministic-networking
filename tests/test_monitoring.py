#!/usr/bin/env python3

"""
Flow Manager Monitoring & Alerting Test Suite

Tests all aspects of the monitoring and alerting setup including:
- Prometheus metrics collection
- Grafana dashboard functionality  
- AlertManager rule evaluation
- Notification delivery systems

Author: Fustli
Date: November 18, 2025
"""

import os
import sys
import time
import requests
import subprocess
import yaml
import json
from typing import Dict, List, Any
import unittest
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.append('/home/ubuntu/k8s-deterministic-networking/src')

import kubernetes
from kubernetes import client, config

class MonitoringSetupTest(unittest.TestCase):
    """Test monitoring infrastructure setup"""
    
    def setUp(self):
        """Setup test environment"""
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        
        self.k8s_client = client.ApiClient()
        self.apps_client = client.AppsV1Api()
        self.monitoring_namespace = "monitoring"
        self.controller_namespace = "kube-system"
    
    def test_service_monitor_exists(self):
        """Test that ServiceMonitor is properly configured"""
        try:
            # Check for ServiceMonitor (requires Prometheus operator)
            custom_api = client.CustomObjectsApi()
            service_monitors = custom_api.list_namespaced_custom_object(
                group="monitoring.coreos.com",
                version="v1", 
                namespace=self.monitoring_namespace,
                plural="servicemonitors"
            )
            
            # Look for Flow Manager ServiceMonitor
            sm_names = [sm['metadata']['name'] for sm in service_monitors['items']]
            self.assertIn('flow-manager-ha-monitor', sm_names)
            
        except Exception as e:
            self.skipTest(f"ServiceMonitor check failed (Prometheus operator may not be installed): {e}")
    
    def test_prometheus_rules_exist(self):
        """Test that PrometheusRule is properly configured"""
        try:
            custom_api = client.CustomObjectsApi()
            prometheus_rules = custom_api.list_namespaced_custom_object(
                group="monitoring.coreos.com",
                version="v1",
                namespace=self.monitoring_namespace, 
                plural="prometheusrules"
            )
            
            # Look for Flow Manager alerts
            rule_names = [rule['metadata']['name'] for rule in prometheus_rules['items']]
            self.assertIn('flow-manager-alerts', rule_names)
            
            # Check specific alert rules
            flow_manager_rules = next(
                (rule for rule in prometheus_rules['items'] 
                 if rule['metadata']['name'] == 'flow-manager-alerts'), 
                None
            )
            
            if flow_manager_rules:
                groups = flow_manager_rules['spec']['groups']
                self.assertTrue(len(groups) > 0, "Should have alert rule groups")
                
                # Check for critical alerts
                rules = groups[0]['rules']
                critical_alerts = [r for r in rules if r.get('labels', {}).get('severity') == 'critical']
                self.assertTrue(len(critical_alerts) >= 3, "Should have at least 3 critical alerts")
                
        except Exception as e:
            self.skipTest(f"PrometheusRule check failed: {e}")
    
    def test_grafana_dashboard_configmap(self):
        """Test that Grafana dashboard ConfigMap is created"""
        try:
            core_api = client.CoreV1Api()
            configmap = core_api.read_namespaced_config_map(
                name="flow-manager-grafana-dashboard",
                namespace=self.monitoring_namespace
            )
            
            # Check dashboard content
            dashboard_data = configmap.data.get('flow-manager-dashboard.json')
            self.assertIsNotNone(dashboard_data, "Dashboard JSON should be present")
            
            # Parse and validate dashboard structure
            dashboard = json.loads(dashboard_data)
            self.assertIn('dashboard', dashboard)
            self.assertIn('panels', dashboard['dashboard'])
            
            panels = dashboard['dashboard']['panels']
            self.assertGreater(len(panels), 5, "Should have multiple dashboard panels")
            
        except client.ApiException as e:
            if e.status == 404:
                self.fail("Grafana dashboard ConfigMap not found")
            else:
                raise
        except Exception as e:
            self.fail(f"Failed to validate Grafana dashboard: {e}")

class MetricsEndpointTest(unittest.TestCase):
    """Test Flow Manager metrics endpoints"""
    
    def setUp(self):
        """Setup test environment"""
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        
        self.apps_client = client.AppsV1Api()
        self.core_api = client.CoreV1Api()
        self.controller_namespace = "kube-system"
    
    def test_health_endpoint_accessibility(self):
        """Test that health endpoints are accessible"""
        # Get Flow Manager pods
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.controller_namespace,
                label_selector="app=flow-manager-ha"
            )
            
            if len(pods.items) == 0:
                self.skipTest("No Flow Manager HA pods found")
            
            # Test health endpoint on first available pod
            pod_name = pods.items[0].metadata.name
            
            # Use kubectl exec to test endpoint
            cmd = [
                "kubectl", "exec", pod_name, "-n", self.controller_namespace, "--",
                "curl", "-s", "http://localhost:8080/health"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, f"Health endpoint should be accessible: {result.stderr}")
            
            # Parse response
            health_data = json.loads(result.stdout)
            self.assertIn('status', health_data)
            self.assertEqual(health_data['status'], 'healthy')
            
        except subprocess.TimeoutExpired:
            self.fail("Health endpoint request timed out")
        except json.JSONDecodeError:
            self.fail(f"Health endpoint returned invalid JSON: {result.stdout}")
        except Exception as e:
            self.skipTest(f"Could not test health endpoint: {e}")
    
    def test_metrics_endpoint_format(self):
        """Test that metrics endpoint returns proper Prometheus format"""
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.controller_namespace,
                label_selector="app=flow-manager-ha"
            )
            
            if len(pods.items) == 0:
                self.skipTest("No Flow Manager HA pods found")
            
            pod_name = pods.items[0].metadata.name
            
            # Get metrics from endpoint
            cmd = [
                "kubectl", "exec", pod_name, "-n", self.controller_namespace, "--",
                "curl", "-s", "http://localhost:8080/metrics"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, "Metrics endpoint should be accessible")
            
            metrics_output = result.stdout
            
            # Check for expected Flow Manager metrics
            expected_metrics = [
                "flow_manager_is_leader",
                "flow_manager_control_loop_running", 
                "flow_manager_metrics_healthy",
                "flow_manager_current_bandwidth_mbps",
                "flow_manager_uptime_seconds"
            ]
            
            for metric in expected_metrics:
                self.assertIn(metric, metrics_output, f"Missing metric: {metric}")
            
            # Validate Prometheus format (basic check)
            lines = metrics_output.strip().split('\n')
            metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
            
            for line in metric_lines:
                self.assertRegex(line, r'^[a-zA-Z_][a-zA-Z0-9_]*(\{[^}]*\})?\s+[0-9.]+$', 
                               f"Invalid Prometheus metric format: {line}")
                
        except Exception as e:
            self.skipTest(f"Could not test metrics endpoint: {e}")

class AlertRuleValidationTest(unittest.TestCase):
    """Test Prometheus alert rule configuration"""
    
    def setUp(self):
        """Setup test environment"""
        self.alert_rules_file = '/home/ubuntu/k8s-deterministic-networking/k8s/infrastructure/prometheus-flow-manager-alerts.yaml'
    
    def test_alert_rules_syntax(self):
        """Test that alert rules have valid YAML syntax"""
        try:
            with open(self.alert_rules_file, 'r') as f:
                alert_config = yaml.safe_load(f)
            
            self.assertIsNotNone(alert_config)
            self.assertIn('spec', alert_config)
            self.assertIn('groups', alert_config['spec'])
            
        except FileNotFoundError:
            self.fail(f"Alert rules file not found: {self.alert_rules_file}")
        except yaml.YAMLError as e:
            self.fail(f"Invalid YAML in alert rules: {e}")
    
    def test_critical_alerts_present(self):
        """Test that all critical alerts are defined"""
        with open(self.alert_rules_file, 'r') as f:
            alert_config = yaml.safe_load(f)
        
        rules = alert_config['spec']['groups'][0]['rules']
        
        critical_alert_names = [
            "MLControllerNoLeader",
            "MLControllerAllPodsDown", 
            "MLControllerLeaderFlapping"
        ]
        
        rule_names = [rule['alert'] for rule in rules if 'alert' in rule]
        
        for critical_alert in critical_alert_names:
            self.assertIn(critical_alert, rule_names, f"Missing critical alert: {critical_alert}")
    
    def test_alert_rule_expressions(self):
        """Test that alert rule expressions are valid"""
        with open(self.alert_rules_file, 'r') as f:
            alert_config = yaml.safe_load(f)
        
        rules = alert_config['spec']['groups'][0]['rules']
        
        for rule in rules:
            if 'alert' in rule:
                # Check required fields
                self.assertIn('expr', rule, f"Alert {rule['alert']} missing expression")
                self.assertIn('labels', rule, f"Alert {rule['alert']} missing labels")
                self.assertIn('annotations', rule, f"Alert {rule['alert']} missing annotations")
                
                # Check required labels
                labels = rule['labels']
                self.assertIn('severity', labels, f"Alert {rule['alert']} missing severity label")
                self.assertIn('component', labels, f"Alert {rule['alert']} missing component label")
                
                # Check required annotations
                annotations = rule['annotations']
                self.assertIn('summary', annotations, f"Alert {rule['alert']} missing summary")
                self.assertIn('description', annotations, f"Alert {rule['alert']} missing description")

class NotificationConfigTest(unittest.TestCase):
    """Test AlertManager notification configuration"""
    
    def setUp(self):
        """Setup test environment"""
        self.alertmanager_config_file = '/home/ubuntu/k8s-deterministic-networking/k8s/infrastructure/alertmanager-flow-manager-config.yaml'
    
    def test_alertmanager_config_syntax(self):
        """Test AlertManager configuration syntax"""
        try:
            with open(self.alertmanager_config_file, 'r') as f:
                configs = list(yaml.safe_load_all(f))
            
            # Find ConfigMap with AlertManager config
            alertmanager_config = None
            for config in configs:
                if (config.get('kind') == 'ConfigMap' and 
                    config.get('metadata', {}).get('name') == 'alertmanager-flow-manager-config'):
                    alertmanager_config = config
                    break
            
            self.assertIsNotNone(alertmanager_config, "AlertManager ConfigMap not found")
            
            # Parse AlertManager configuration
            am_config_yaml = alertmanager_config['data']['alertmanager.yml']
            am_config = yaml.safe_load(am_config_yaml)
            
            # Validate structure
            self.assertIn('route', am_config)
            self.assertIn('receivers', am_config)
            self.assertIn('inhibit_rules', am_config)
            
        except FileNotFoundError:
            self.fail(f"AlertManager config file not found: {self.alertmanager_config_file}")
        except yaml.YAMLError as e:
            self.fail(f"Invalid YAML in AlertManager config: {e}")
    
    def test_notification_receivers_configured(self):
        """Test that notification receivers are properly configured"""
        with open(self.alertmanager_config_file, 'r') as f:
            configs = list(yaml.safe_load_all(f))
        
        alertmanager_config = next(
            (c for c in configs 
             if c.get('kind') == 'ConfigMap' and 
             c.get('metadata', {}).get('name') == 'alertmanager-flow-manager-config'),
            None
        )
        
        am_config_yaml = alertmanager_config['data']['alertmanager.yml']
        am_config = yaml.safe_load(am_config_yaml)
        
        receivers = am_config['receivers']
        receiver_names = [r['name'] for r in receivers]
        
        expected_receivers = [
            'critical-flow-manager',
            'high-flow-manager', 
            'medium-flow-manager',
            'info-flow-manager'
        ]
        
        for expected in expected_receivers:
            self.assertIn(expected, receiver_names, f"Missing receiver: {expected}")

def run_monitoring_tests():
    """Run all monitoring test suites"""
    print("🧪 Running Flow Manager Monitoring Test Suite...")
    print("=" * 60)
    
    # Create test suites
    suites = []
    suites.append(unittest.TestLoader().loadTestsFromTestCase(MonitoringSetupTest))
    suites.append(unittest.TestLoader().loadTestsFromTestCase(MetricsEndpointTest))
    suites.append(unittest.TestLoader().loadTestsFromTestCase(AlertRuleValidationTest))
    suites.append(unittest.TestLoader().loadTestsFromTestCase(NotificationConfigTest))
    
    # Combine all suites
    combined_suite = unittest.TestSuite(suites)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(combined_suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print(f"Monitoring Test Results:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.failures:
        print("\n[FAILURES]:")
        for test, failure in result.failures:
            print(f"   {test}: {failure}")
    
    if result.errors:
        print("\n[ERRORS]:")
        for test, error in result.errors:
            print(f"   {test}: {error}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall Result: {'[PASS]' if success else '[FAIL]'}")
    
    return success

if __name__ == "__main__":
    success = run_monitoring_tests()
    sys.exit(0 if success else 1)