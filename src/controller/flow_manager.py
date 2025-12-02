#!/usr/bin/env python3
"""
Production-Grade Deterministic Networking Flow Manager for Kubernetes
Version: 5.0 (Multi-App Config-Driven Mode)

Monitors multiple critical applications defined in critical-apps.yaml
Calculates jitter from network-probe raw latency measurements
Makes control decisions based on SLA violations
Dynamically patches best-effort deployment annotations
"""

import os
import sys
import time
import logging
import requests
from typing import Dict, Optional, Tuple
from collections import deque
from kubernetes import client, config as k8s_config
from prometheus_client import start_http_server, Gauge

# Import config loader
sys.path.insert(0, '/app')
from config_loader import ConfigLoader, SystemConfig, CriticalAppConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)
logger = logging.getLogger("FlowManager")

# Prometheus metrics - exported by flow manager
udp_jitter_gauge = Gauge(
    'flowmanager_udp_jitter_ms',
    'UDP jitter calculated by flow manager (used for control decisions)',
    ['service', 'target_host']
)

tcp_jitter_gauge = Gauge(
    'flowmanager_tcp_jitter_ms',
    'TCP jitter calculated by flow manager (monitoring only)',
    ['service', 'target_host']
)

bandwidth_limit_gauge = Gauge(
    'flowmanager_bandwidth_limit_mbps',
    'Current bandwidth limit enforced by flow manager',
    ['deployment', 'namespace']
)


class MetricsClient:
    """Fetches raw latency measurements from network-probe service"""
    
    def __init__(self, probe_service: str, window_size: int):
        self.probe_url = f"http://{probe_service}/metrics"
        self.windows = {}  # Per-app rolling windows
        self.window_size = window_size
        logger.info(f"MetricsClient initialized: probe={probe_service}, window_size={window_size}")
    
    def fetch_and_calculate_jitter(self, app: CriticalAppConfig) -> Optional[Tuple[float, float]]:
        """
        Fetch raw latency for app and calculate jitter locally
        Returns: (latency_ms, jitter_ms) or None on failure
        """
        try:
            response = requests.get(self.probe_url, timeout=2.0)
            response.raise_for_status()
            
            # Parse Prometheus text format - look for UDP or TCP latency
            if app.protocol.upper() == 'UDP':
                metric_name = 'network_probe_udp_latency_ms'
            elif app.protocol.upper() == 'TCP':
                metric_name = 'network_probe_tcp_latency_ms'
            else:
                logger.error(f"Unknown protocol {app.protocol} for {app.name}")
                return None
            
            latency = None
            for line in response.text.split('\n'):
                if line.startswith(metric_name + '{'):
                    latency = float(line.split()[-1])
                    break
            
            if latency is None:
                logger.debug(f"No latency metric found for {app.name} ({app.protocol})")
                return None
            
            # Initialize window if first measurement
            if app.name not in self.windows:
                self.windows[app.name] = deque(maxlen=self.window_size)
            
            # Add to rolling window
            self.windows[app.name].append(latency)
            
            # Calculate jitter (IQR method)
            if len(self.windows[app.name]) >= 5:
                jitter = self._calculate_jitter_iqr(self.windows[app.name])
                return (latency, jitter)
            else:
                # Not enough samples yet
                return (latency, 0.0)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch metrics for {app.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing metrics for {app.name}: {e}")
            return None
    
    def _calculate_jitter_iqr(self, window: deque) -> float:
        """Calculate jitter using Interquartile Range (robust to outliers)"""
        if len(window) < 5:
            return 0.0
        
        sorted_samples = sorted(window)
        n = len(sorted_samples)
        
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        
        q1 = sorted_samples[q1_idx]
        q3 = sorted_samples[q3_idx]
        
        iqr = q3 - q1
        return round(iqr, 3)


class BandwidthController:
    """
    Multi-Application Bandwidth Controller
    Monitors all critical apps and throttles best-effort deployments
    """
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.metrics_client = MetricsClient(
            probe_service=os.getenv('PROBE_SERVICE', 'network-probe-svc.default.svc.cluster.local:9090'),
            window_size=config.control.window_size
        )
        
        # Initialize Kubernetes client
        try:
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except:
            k8s_config.load_kube_config()
            logger.info("Loaded local kubeconfig")
        
        self.apps_v1 = client.AppsV1Api()
        
        # Current bandwidth state (per best-effort deployment)
        self.current_bandwidths = {}
        for target in config.best_effort_targets:
            bw = self._get_current_bandwidth(target.deployment, target.namespace)
            self.current_bandwidths[target.deployment] = bw if bw else target.initial_bandwidth
        
        logger.info(f"Controller initialized with {len(config.critical_apps)} critical apps")
        logger.info(f"Initial bandwidths: {self.current_bandwidths}")
    
    def _get_current_bandwidth(self, deployment: str, namespace: str) -> Optional[int]:
        """Read current bandwidth annotation from deployment"""
        try:
            dep = self.apps_v1.read_namespaced_deployment(deployment, namespace)
            annotations = dep.spec.template.metadata.annotations or {}
            bw_str = annotations.get('kubernetes.io/egress-bandwidth', '0M')
            return int(bw_str.replace('M', '').replace('m', '').replace('G', '000').replace('g', '000'))
        except Exception as e:
            logger.warning(f"Failed to read bandwidth for {deployment}: {e}")
            return None
    
    def control_loop(self):
        """Main control loop - monitors all critical apps and adjusts bandwidth"""
        cycle = 0
        
        logger.info("="*60)
        logger.info("Starting Multi-App Bandwidth Controller")
        logger.info(f"Monitoring {len(self.config.critical_apps)} critical applications:")
        for app in self.config.critical_apps:
            logger.info(f"  - {app.name}: max_jitter={app.max_jitter_ms}ms, priority={app.priority}")
        logger.info(f"Best-effort targets: {[t.deployment for t in self.config.best_effort_targets]}")
        logger.info("="*60)
        
        while True:
            cycle += 1
            logger.info(f"\n--- Cycle {cycle} ---")
            
            # Step 1: Measure all critical apps
            app_states = {}
            for app in self.config.critical_apps:
                result = self.metrics_client.fetch_and_calculate_jitter(app)
                if result:
                    latency, jitter = result
                    violation = jitter > app.max_jitter_ms
                    severity = jitter / app.max_jitter_ms if violation else 0.0
                    
                    app_states[app.name] = {
                        'app': app,
                        'latency': latency,
                        'jitter': jitter,
                        'violation': violation,
                        'severity': severity
                    }
                    
                    # Export jitter metrics used for control decisions
                    if app.protocol.upper() == 'UDP':
                        udp_jitter_gauge.labels(
                            service=app.name,
                            target_host=app.service
                        ).set(jitter)
                    elif app.protocol.upper() == 'TCP':
                        tcp_jitter_gauge.labels(
                            service=app.name,
                            target_host=app.service
                        ).set(jitter)
                    
                    status = "VIOLATION" if violation else "OK"
                    logger.info(f"  {app.name}: latency={latency:.2f}ms, jitter={jitter:.3f}ms "
                               f"(threshold={app.max_jitter_ms}ms) [{status}]")
            
            if not app_states:
                logger.warning("No app measurements available, skipping cycle")
                time.sleep(self.config.control.control_interval)
                continue
            
            # Step 2: Aggregate violations (use highest priority app's state)
            decision = self._make_control_decision(app_states)
            
            # Step 3: Apply bandwidth adjustments
            self._apply_bandwidth_changes(decision)
            
            time.sleep(self.config.control.control_interval)
    
    def _make_control_decision(self, app_states: Dict) -> Dict:
        """
        Decide bandwidth adjustment using Asymmetric AIMD algorithm
        
        Algorithm: "Cut deep when unsafe, recover slowly when safe"
        - If violation: Decrease by 20% (multiplicative decrease)
        - If stable: Increase by 10 Mbps (additive increase)
        
        Only UDP apps are used for bandwidth control decisions (real-time traffic)
        TCP apps are monitored but don't trigger throttling
        
        Returns: {'action': 'throttle'|'release'|'maintain', 'reason': str, 'reduction_percent': float}
        """
        
        # Find worst violation among UDP apps only (highest priority UDP app that violates SLA)
        worst_violation = None
        for state in app_states.values():
            if state['violation'] and state['app'].protocol.upper() == 'UDP':
                if worst_violation is None or state['app'].priority > worst_violation['app'].priority:
                    worst_violation = state
        
        if worst_violation:
            # ASYMMETRIC AIMD: Multiplicative Decrease (20%)
            # This is the "cut deep when unsafe" part
            return {
                'action': 'throttle',
                'reason': f"{worst_violation['app'].name} {worst_violation['app'].protocol} jitter {worst_violation['jitter']:.3f}ms > {worst_violation['app'].max_jitter_ms}ms",
                'reduction_percent': 0.20  # 20% reduction for safety
            }
        
        # Check if all UDP apps are performing well (stable condition)
        # Consider stable if jitter < 50% of threshold
        # Only check UDP apps for control decisions
        udp_states = [state for state in app_states.values() if state['app'].protocol.upper() == 'UDP']
        all_stable = all(
            state['jitter'] < (state['app'].max_jitter_ms * 0.5)
            for state in udp_states
        ) if udp_states else False
        
        if all_stable:
            # ASYMMETRIC AIMD: Additive Increase (10 Mbps)
            # This is the "recover slowly when safe" part
            return {
                'action': 'release',
                'reason': 'All critical apps stable (jitter < 50% threshold)',
                'reduction_percent': 0.0  # Not used for release
            }
        
        return {
            'action': 'maintain',
            'reason': 'Apps within acceptable range',
            'reduction_percent': 0.0
        }
    
    def _apply_bandwidth_changes(self, decision: Dict):
        """
        Apply bandwidth changes using Asymmetric AIMD algorithm
        
        Throttle: Multiplicative Decrease (20% reduction)
        Release: Additive Increase (10 Mbps increase)
        """
        
        action = decision['action']
        reason = decision['reason']
        reduction_percent = decision['reduction_percent']
        
        logger.info(f"Decision: {action.upper()} - {reason}")
        
        if action == 'maintain':
            logger.info(f"Bandwidth maintained: {self.current_bandwidths}")
            return
        
        for target in self.config.best_effort_targets:
            current_bw = self.current_bandwidths[target.deployment]
            
            if action == 'throttle':
                # ASYMMETRIC AIMD: Multiplicative Decrease
                # Limit_new = Limit_old - (Limit_old × 0.20)
                # This ensures we can never reach 0 (always keeps 80% minimum)
                reduction = int(current_bw * reduction_percent)
                new_bw = current_bw - reduction
                # Ensure we don't go below minimum
                new_bw = max(self.config.control.min_bandwidth, new_bw)
                
            elif action == 'release':
                # ASYMMETRIC AIMD: Additive Increase
                # Limit_new = Limit_old + 10 Mbps
                # Slow, steady recovery for stability
                new_bw = current_bw + 10  # Fixed 10 Mbps increase
                # Ensure we don't exceed maximum
                new_bw = min(self.config.control.max_bandwidth, new_bw)
            
            if new_bw != current_bw:
                success = self._patch_deployment_bandwidth(
                    target.deployment,
                    target.namespace,
                    new_bw
                )
                
                if success:
                    delta = new_bw - current_bw
                    if action == 'throttle':
                        logger.info(f"  {target.deployment}: {current_bw}M -> {new_bw}M ({delta:+d}M, -{reduction_percent*100:.0f}% cut)")
                    else:
                        logger.info(f"  {target.deployment}: {current_bw}M -> {new_bw}M ({delta:+d}M, +10M additive)")
                    self.current_bandwidths[target.deployment] = new_bw
                    
                    # Export bandwidth limit metric
                    bandwidth_limit_gauge.labels(
                        deployment=target.deployment,
                        namespace=target.namespace
                    ).set(new_bw)
            else:
                logger.info(f"  {target.deployment}: At limit ({new_bw}M)")
    
    def _patch_deployment_bandwidth(self, deployment: str, namespace: str, bandwidth_mbps: int) -> bool:
        """Patch deployment annotation to set egress bandwidth"""
        try:
            patch_body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubernetes.io/egress-bandwidth": f"{bandwidth_mbps}M"
                            }
                        }
                    }
                }
            }
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment,
                namespace=namespace,
                body=patch_body
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to patch {deployment}: {e}")
            return False


def calculate_bandwidth_limit(current_limit_mbps: int, jitter_ms: float, throughput_mbps: float) -> int:
    """
    Asymmetric AIMD (Additive Increase Multiplicative Decrease) Control Algorithm
    
    Implements aggressive throttling on congestion and slow recovery during healthy periods.
    This asymmetric approach provides fast congestion response while maintaining stability.
    
    Args:
        current_limit_mbps: Current bandwidth limit in Mbps
        jitter_ms: Measured UDP jitter in milliseconds
        throughput_mbps: Measured TCP throughput in Mbps
    
    Returns:
        New bandwidth limit in Mbps (clamped between 10-1000 Mbps)
    
    Algorithm:
        - If congestion detected (high jitter OR low throughput):
          Decrease by 100 Mbps (aggressive throttle)
        - If healthy:
          Increase by 10 Mbps (slow recovery)
    """
    # SLA thresholds
    MAX_JITTER = 5.0  # milliseconds
    MIN_THROUGHPUT = 50.0  # Mbps
    
    # Bandwidth range
    MIN_BW = 10  # Mbps
    MAX_BW = 1000  # Mbps
    
    # Control step sizes (asymmetric)
    THROTTLE_STEP = 100  # Mbps - aggressive decrease
    RECOVERY_STEP = 10   # Mbps - conservative increase
    
    # Check for SLA violations (congestion indicators)
    jitter_violation = jitter_ms > MAX_JITTER
    throughput_violation = throughput_mbps < MIN_THROUGHPUT
    
    if jitter_violation or throughput_violation:
        # CONGESTION DETECTED: Aggressive throttling
        new_limit = current_limit_mbps - THROTTLE_STEP
    else:
        # HEALTHY: Slow recovery
        new_limit = current_limit_mbps + RECOVERY_STEP
    
    # Clamp to valid bandwidth range
    new_limit = max(MIN_BW, min(MAX_BW, new_limit))
    
    return new_limit


def main():
    """Entry point"""
    config_path = os.getenv('CONFIG_PATH', '/etc/flowmanager/critical-apps.yaml')
    
    try:
        # Start Prometheus metrics server
        metrics_port = int(os.getenv('METRICS_PORT', '8001'))
        start_http_server(metrics_port)
        logger.info(f"Started Prometheus metrics server on port {metrics_port}")
        
        # Load configuration
        config = ConfigLoader.load(config_path)
        
        if not ConfigLoader.validate(config):
            logger.error("Configuration validation failed")
            sys.exit(1)
        
        logger.info(f"Loaded configuration for {len(config.critical_apps)} critical apps:")
        for app in config.critical_apps:
            logger.info(f"  - {app.name}: max_jitter={app.max_jitter_ms}ms (priority={app.priority})")
        
        # Start controller
        controller = BandwidthController(config)
        controller.control_loop()
        
    except KeyboardInterrupt:
        logger.info("\nShutting down controller")
    except Exception as e:
        logger.error(f"Controller startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
