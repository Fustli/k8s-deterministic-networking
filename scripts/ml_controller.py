#!/usr/bin/env python3

"""
Deterministic Networking ML Controller for Kubernetes

This controller implements a feedback control loop that dynamically adjusts network bandwidth
for best-effort applications while ensuring QoS guarantees for critical applications.

Key components:
- Prometheus/Hubble integration for real-time latency monitoring
- Kubernetes bandwidth control via pod annotations
- Proportional control algorithm for bandwidth adjustment

Author: Fustli
Date: November 10, 2025
"""

import os
import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import kubernetes
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ControlParameters:
    """Configuration parameters for the control loop"""
    TARGET_JITTER_MS: float = 1.0    # Target jitter threshold in milliseconds
    MIN_BANDWIDTH_MBPS: int = 10     # Minimum allowed bandwidth
    MAX_BANDWIDTH_MBPS: int = 1000   # Maximum allowed bandwidth
    DECREASE_STEP_MBPS: int = 50     # How much to decrease bandwidth when jitter is high
    INCREASE_STEP_MBPS: int = 10     # How much to increase bandwidth when jitter is low
    UPDATE_THRESHOLD_MBPS: int = 5   # Minimum bandwidth change to trigger an update
    CONTROL_INTERVAL_SEC: int = 5    # How often to run the control loop

@dataclass
class KubernetesConfig:
    """Kubernetes-related configuration"""
    DEPLOYMENT_NAME: str = "telemetry-upload-deployment"
    NAMESPACE: str = "default"
    BANDWIDTH_ANNOTATION: str = "kubernetes.io/egress-bandwidth"

class PrometheusMetrics:
    """Handles all Prometheus/Hubble metric queries and processing"""
    
    def __init__(self, prometheus_url: str):
        """Initialize Prometheus client connection"""
        self.prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)
        
    def get_critical_app_latency(self) -> float:
        """
        Query Prometheus/Hubble for UDP jitter metrics of the robot-control application.
        
        Returns:
            float: 95th percentile jitter in milliseconds
            
        Note:
            Returns a default value of 0.5ms if the query fails, allowing the
            system to continue operating with a conservative estimate.
        """
        try:
            # PromQL query for Hubble metrics
            # Note: The exact metric name and labels will need to be adjusted based on your Hubble setup
            query = """
            histogram_quantile(0.95, sum(
                rate(hubble_flow_latency_seconds_bucket{
                    source_pod=~"robot-control.*",
                    protocol="UDP"
                }[1m]
            ) by (le))
            """
            # Use the Prometheus client attached to this instance
            result = self.prom.custom_query(query)

            if result and len(result) > 0:
                # Convert seconds to milliseconds
                latency_ms = float(result[0]['value'][1]) * 1000
                return latency_ms

            logger.warning("No data returned from Prometheus query")
            return 0.5

        except Exception as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return 0.5

class BandwidthController:
    """
    Main controller class implementing the bandwidth control loop.
    Uses a proportional control algorithm to adjust bandwidth based on observed jitter.
    """
    
    def __init__(self):
        """Initialize the controller with necessary clients and configurations"""
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()  # Running inside cluster
        except config.ConfigException:
            config.load_kube_config()       # Running locally
            
        # Initialize clients and configurations
        self.k8s_client = client.AppsV1Api()
        self.metrics = PrometheusMetrics(
            os.getenv('PROMETHEUS_URL', 'http://prometheus-server:9090')
        )
        self.control_params = ControlParameters()
        self.k8s_config = KubernetesConfig()
        
        # Initialize controller state
        self.current_bandwidth = 100  # Starting bandwidth in Mbps
        
    def adjust_bandwidth(self, current_jitter: float) -> int:
        """
        Calculate new bandwidth based on observed jitter using proportional control.
        
        Args:
            current_jitter: Measured jitter in milliseconds
            
        Returns:
            int: New bandwidth value in Mbps
        """
        if current_jitter > self.control_params.TARGET_JITTER_MS:
            # Reduce bandwidth when jitter exceeds target
            new_bandwidth = self.current_bandwidth - self.control_params.DECREASE_STEP_MBPS
        else:
            # Gradually increase bandwidth when jitter is under control
            new_bandwidth = self.current_bandwidth + self.control_params.INCREASE_STEP_MBPS
            
        # Ensure bandwidth stays within defined bounds
        return max(
            self.control_params.MIN_BANDWIDTH_MBPS,
            min(new_bandwidth, self.control_params.MAX_BANDWIDTH_MBPS)
        )

    def update_deployment_bandwidth(self, bandwidth_mbps: int) -> bool:
        """
        Update the Kubernetes deployment with new bandwidth annotation.
        
        Args:
            bandwidth_mbps: New bandwidth limit in Mbps
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            # Fetch current deployment
            deployment = self.k8s_client.read_namespaced_deployment(
                name=self.k8s_config.DEPLOYMENT_NAME,
                namespace=self.k8s_config.NAMESPACE
            )
            
            # Ensure metadata and annotations exist
            if deployment.spec.template.metadata is None:
                deployment.spec.template.metadata = client.V1ObjectMeta()
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}
            
            # Update bandwidth annotation
            deployment.spec.template.metadata.annotations[
                self.k8s_config.BANDWIDTH_ANNOTATION
            ] = f"{bandwidth_mbps}M"
            
            # Apply the update
            self.k8s_client.patch_namespaced_deployment(
                name=self.k8s_config.DEPLOYMENT_NAME,
                namespace=self.k8s_config.NAMESPACE,
                body=deployment
            )
            
            logger.info(f"Updated bandwidth limit to {bandwidth_mbps}Mbps")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update deployment: {e}")
            return False

def main():
    """Entry point for the controller: instantiate and run the BandwidthController."""
    controller = BandwidthController()
    controller.run()


if __name__ == "__main__":
    main()
