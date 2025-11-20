#!/usr/bin/env python3
"""
Simple Prometheus exporter for bandwidth annotations
Exposes current bandwidth limits as Prometheus metrics
"""

import time
from kubernetes import client, config
from prometheus_client import start_http_server, Gauge
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
bandwidth_limit = Gauge(
    'kubernetes_deployment_bandwidth_limit_mbps',
    'Current egress bandwidth limit in Mbps',
    ['namespace', 'deployment']
)

def get_bandwidth_limits():
    """Query all deployments and extract bandwidth annotations"""
    try:
        v1 = client.AppsV1Api()
        
        # Get all deployments in default namespace
        deployments = v1.list_namespaced_deployment(namespace='default')
        
        for dep in deployments.items:
            if dep.spec.template.metadata.annotations:
                bw_annotation = dep.spec.template.metadata.annotations.get('kubernetes.io/egress-bandwidth')
                if bw_annotation:
                    # Parse bandwidth (e.g., "385M" -> 385)
                    bw_mbps = int(bw_annotation.rstrip('M'))
                    
                    # Update Prometheus metric
                    bandwidth_limit.labels(
                        namespace=dep.metadata.namespace,
                        deployment=dep.metadata.name
                    ).set(bw_mbps)
                    
                    logger.debug(f"{dep.metadata.name}: {bw_mbps}Mbps")
    
    except Exception as e:
        logger.error(f"Error collecting metrics: {e}")

def main():
    """Start the exporter"""
    # Load Kubernetes config
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    
    # Start Prometheus HTTP server on port 8000
    start_http_server(8000)
    logger.info("Bandwidth exporter started on port 8000")
    
    # Update metrics every 5 seconds
    while True:
        get_bandwidth_limits()
        time.sleep(5)

if __name__ == '__main__':
    main()
