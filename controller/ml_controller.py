#!/usr/bin/env python3

"""
Production-Grade Deterministic Networking ML Controller for Kubernetes

Implements intelligent bandwidth control using real Hubble network metrics:
- IQR-based jitter calculation for congestion detection
- EWMA signal smoothing to reduce measurement noise  
- Hysteresis control to prevent bandwidth oscillation

Requires real Hubble metrics via Prometheus - no synthetic fallbacks.
"""

import os
import time
import logging
from typing import Optional, Tuple, Dict, Union, Any
from pathlib import Path

from kubernetes import client, config
from prometheus_api_client import PrometheusConnect

# Constants
DEFAULT_ENV_FILE = '.env'
DEFAULT_LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
METRICS_UNAVAILABLE_RETRY_DELAY = 30

logging.basicConfig(
    level=logging.INFO,
    format=DEFAULT_LOG_FORMAT
)
logger = logging.getLogger(__name__)

def load_env_config(env_file_path: Optional[str] = None) -> Dict[str, str]:
    """
    Load configuration from .env file.
    
    Args:
        env_file_path: Path to .env file. If None, looks for .env in config directory
        
    Returns:
        Dict[str, str]: Configuration key-value pairs
    """
    if env_file_path is None:
        script_dir = Path(__file__).parent.parent  # Go up to project root
        env_file_path = script_dir / 'config' / DEFAULT_ENV_FILE
    
    config_dict = {}
    
    try:
        with open(env_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    config_dict[key.strip()] = value.strip()
        
        logger.info(f"Loaded configuration from {env_file_path}")
        return config_dict
        
    except FileNotFoundError:
        logger.warning(f"Configuration file {env_file_path} not found. Using environment variables only.")
        return {}
    except Exception as e:
        logger.error(f"Error loading configuration file {env_file_path}: {e}")
        return {}

def get_config_value(
    key: str, 
    default_value: Any, 
    config_dict: Dict[str, str], 
    value_type: type = str
) -> Any:
    """
    Get configuration value from .env file, environment variables, or default.
    
    Priority: Environment Variables > .env file > default value
    
    Args:
        key: Configuration key
        default_value: Default value if not found
        config_dict: Configuration loaded from .env file
        value_type: Type to convert value to (str, int, float, bool)
        
    Returns:
        Configuration value with proper type conversion
    """
    env_value = os.environ.get(key)
    
    if env_value is None:
        value = config_dict.get(key)
    else:
        value = env_value
    
    if value is None:
        return default_value
    
    try:
        if value_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        else:
            return str(value)
    except ValueError as e:
        logger.warning(f"Invalid value for {key}: {value}. Using default: {default_value}")
        return default_value

class ControllerConfig:
    """
    Production controller configuration loaded from .env file and environment variables.
    
    Priority: Environment Variables > .env file > default values
    """
    
    def __init__(self, env_file_path: str = None):
        """Initialize configuration from .env file and environment variables"""
        # Load .env file
        config_dict = load_env_config(env_file_path)
        
        self.PROMETHEUS_URL = get_config_value(
            'PROMETHEUS_URL', 'http://prometheus-server:9090', config_dict, str
        )
        self.TARGET_APPLICATION = get_config_value(
            'TARGET_APPLICATION', 'robot-factory', config_dict, str
        )
        
        self.TARGET_JITTER_MS = get_config_value(
            'TARGET_JITTER_MS', 2.0, config_dict, float
        )
        self.TARGET_LATENCY_MS = get_config_value(
            'TARGET_LATENCY_MS', 10.0, config_dict, float
        )
        
        self.MIN_BANDWIDTH_MBPS = get_config_value(
            'MIN_BANDWIDTH_MBPS', 10, config_dict, int
        )
        self.MAX_BANDWIDTH_MBPS = get_config_value(
            'MAX_BANDWIDTH_MBPS', 1000, config_dict, int
        )
        self.AGGRESSIVE_DECREASE_MBPS = get_config_value(
            'AGGRESSIVE_DECREASE_MBPS', 100, config_dict, int
        )
        self.GENTLE_DECREASE_MBPS = get_config_value(
            'GENTLE_DECREASE_MBPS', 20, config_dict, int
        )
        self.INCREASE_STEP_MBPS = get_config_value(
            'INCREASE_STEP_MBPS', 15, config_dict, int
        )
        self.UPDATE_THRESHOLD_MBPS = get_config_value(
            'UPDATE_THRESHOLD_MBPS', 5, config_dict, int
        )
        
        self.CONTROL_INTERVAL_SEC = get_config_value(
            'CONTROL_INTERVAL_SEC', 5, config_dict, int
        )
        
        self.EWMA_ALPHA = get_config_value(
            'EWMA_ALPHA', 0.7, config_dict, float
        )
        
        self.COOLDOWN_PERIOD_SEC = get_config_value(
            'COOLDOWN_PERIOD_SEC', 30, config_dict, int
        )
        self.CRITICAL_JITTER_MULTIPLIER = get_config_value(
            'CRITICAL_JITTER_MULTIPLIER', 3.0, config_dict, float
        )
        
        self.DEPLOYMENT_NAME = get_config_value(
            'DEPLOYMENT_NAME', 'telemetry-upload-deployment', config_dict, str
        )
        self.NAMESPACE = get_config_value(
            'NAMESPACE', 'default', config_dict, str
        )
        self.BANDWIDTH_ANNOTATION = get_config_value(
            'BANDWIDTH_ANNOTATION', 'kubernetes.io/egress-bandwidth', config_dict, str
        )
        
        log_level = get_config_value('LOG_LEVEL', 'INFO', config_dict, str)
        logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        self._log_configuration()
    
    def _log_configuration(self):
        """Log the loaded configuration for verification"""
        logger.info("Production ML Controller Configuration:")
        logger.info(f"  Prometheus URL: {self.PROMETHEUS_URL}")
        logger.info(f"  Target Application: {self.TARGET_APPLICATION}")
        logger.info(f"  Target Jitter: {self.TARGET_JITTER_MS}ms")
        logger.info(f"  Target Latency: {self.TARGET_LATENCY_MS}ms")
        logger.info(f"  Bandwidth Range: {self.MIN_BANDWIDTH_MBPS}-{self.MAX_BANDWIDTH_MBPS} Mbps")
        logger.info(f"  EWMA Alpha: {self.EWMA_ALPHA}")
        logger.info(f"  Cooldown Period: {self.COOLDOWN_PERIOD_SEC}s")
        logger.info(f"  Deployment: {self.NAMESPACE}/{self.DEPLOYMENT_NAME}")

class PrometheusMetrics:
    """Handles all Prometheus/Hubble metric queries and processing"""
    
    def __init__(self, config: ControllerConfig):
        """Initialize Prometheus client connection"""
        self.prom = PrometheusConnect(url=config.PROMETHEUS_URL, disable_ssl=True)
        self.target_app = config.TARGET_APPLICATION
        
    def get_latency_metrics(self) -> Tuple[float, float]:
        """
        Query Prometheus for true jitter calculation using IQR and P95 latency.
        
        Returns:
            Tuple[float, float]: (jitter_ms, p95_latency_ms)
            - jitter_ms: True jitter calculated as Q3 - Q1 (IQR)
            - p95_latency_ms: 95th percentile latency
            
        Raises:
            RuntimeError: If real metrics are not available from Hubble
        """
        jitter_ms, p95_latency_ms = self._get_hubble_latency_metrics()
        
        if jitter_ms is not None and p95_latency_ms is not None:
            logger.debug(f"Real metrics - Jitter: {jitter_ms:.2f}ms, P95 Latency: {p95_latency_ms:.2f}ms")
            return jitter_ms, p95_latency_ms
        
        raise RuntimeError("Real Hubble metrics not available. Production controller requires real network data.")
    
    def _get_hubble_latency_metrics(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Try to get real latency metrics from Hubble for true jitter calculation.
        
        Returns:
            Tuple[Optional[float], Optional[float]]: (jitter_ms, p95_latency_ms) or (None, None)
        """
        try:
            # Query for Q1 (25th percentile) latency from Hubble
            q1_query = f'''
            histogram_quantile(0.25, 
                rate(hubble_http_request_duration_seconds_bucket{{
                    destination_app="{self.target_app}"
                }}[5m])
            ) * 1000
            '''
            
            # Query for Q3 (75th percentile) latency from Hubble  
            q3_query = f'''
            histogram_quantile(0.75, 
                rate(hubble_http_request_duration_seconds_bucket{{
                    destination_app="{self.target_app}"
                }}[5m])
            ) * 1000
            '''
            
            # Query for P95 latency from Hubble
            p95_query = f'''
            histogram_quantile(0.95, 
                rate(hubble_http_request_duration_seconds_bucket{{
                    destination_app="{self.target_app}"
                }}[5m])
            ) * 1000
            '''
            
            q1_result = self.prom.custom_query(q1_query)
            q3_result = self.prom.custom_query(q3_query)
            p95_result = self.prom.custom_query(p95_query)
            
            if (q1_result and len(q1_result) > 0 and 
                q3_result and len(q3_result) > 0 and 
                p95_result and len(p95_result) > 0):
                
                q1_latency = float(q1_result[0]['value'][1])
                q3_latency = float(q3_result[0]['value'][1])
                p95_latency = float(p95_result[0]['value'][1])
                
                # Calculate true jitter as IQR
                jitter_ms = q3_latency - q1_latency
                
                # Ensure jitter is non-negative
                jitter_ms = max(0, jitter_ms)
                
                return jitter_ms, p95_latency
                
        except Exception as e:
            logger.debug(f"Hubble latency query failed: {e}")
            
        return None, None

class BandwidthController:
    """
    Production-grade controller implementing:
    1. True jitter calculation using IQR (Q3 - Q1)
    2. Signal smoothing with EWMA (Exponential Weighted Moving Average) 
    3. Hysteresis to prevent oscillation with cooldown periods
    
    Uses intelligent bandwidth control based on distinguishing between:
    - Congestion (high jitter) -> Aggressive throttling
    - Distance/Processing latency (high P95, low jitter) -> Gentle or no throttling
    """
    
    def __init__(self, config_file_path: str = None):
        """Initialize the controller with configuration from .env file"""
        # Load configuration
        self.config = ControllerConfig(config_file_path)
        
        # Load Kubernetes configuration
        try:
            config.load_incluster_config()  # Running inside cluster
        except config.ConfigException:
            config.load_kube_config()       # Running locally
            
        # Initialize clients
        self.k8s_client = client.AppsV1Api()
        self.metrics = PrometheusMetrics(self.config)
        
        # Initialize controller state
        self.current_bandwidth = 100  # Starting bandwidth in Mbps
        
        # EWMA smoothing state
        self.smoothed_jitter: Optional[float] = None
        self.smoothed_latency: Optional[float] = None
        
        # Hysteresis state
        self.last_change_time: Optional[float] = None
        self.last_bandwidth_change: int = 0  # Track direction: -1 decrease, 0 none, +1 increase
    
    def apply_ewma_smoothing(self, raw_jitter: float, raw_latency: float) -> Tuple[float, float]:
        """
        Apply Exponential Weighted Moving Average (EWMA) smoothing to reduce noise.
        
        Formula: New_Value = (Current_Measure * alpha) + (Old_Value * (1-alpha))
        
        Args:
            raw_jitter: Current raw jitter measurement
            raw_latency: Current raw latency measurement
            
        Returns:
            Tuple[float, float]: (smoothed_jitter, smoothed_latency)
        """
        alpha = self.config.EWMA_ALPHA
        
        if self.smoothed_jitter is None:
            # First measurement - no history to smooth with
            self.smoothed_jitter = raw_jitter
            self.smoothed_latency = raw_latency
        else:
            # Apply EWMA smoothing
            self.smoothed_jitter = (raw_jitter * alpha) + (self.smoothed_jitter * (1 - alpha))
            self.smoothed_latency = (raw_latency * alpha) + (self.smoothed_latency * (1 - alpha))
        
        logger.debug(f"EWMA smoothing: Raw({raw_jitter:.2f}, {raw_latency:.2f}) -> "
                    f"Smoothed({self.smoothed_jitter:.2f}, {self.smoothed_latency:.2f})")
        
        return self.smoothed_jitter, self.smoothed_latency
    
    def should_respect_cooldown(self, current_jitter: float) -> bool:
        """
        Check if we should respect the cooldown period for bandwidth increases.
        
        Args:
            current_jitter: Current jitter measurement
            
        Returns:
            bool: True if cooldown should be respected, False if we can override it
        """
        if self.last_change_time is None:
            return False  # No previous changes
        
        time_since_change = time.time() - self.last_change_time
        
        # Always allow decreases immediately (safety first)
        if self.last_bandwidth_change <= 0:
            return False
        
        # Check if we're in cooldown period
        in_cooldown = time_since_change < self.config.COOLDOWN_PERIOD_SEC
        
        # Override cooldown if jitter is critically high
        critical_jitter_threshold = (self.config.TARGET_JITTER_MS * 
                                   self.config.CRITICAL_JITTER_MULTIPLIER)
        jitter_is_critical = current_jitter >= critical_jitter_threshold
        
        if in_cooldown and jitter_is_critical:
            logger.warning(f"Overriding cooldown due to critical jitter: {current_jitter:.2f}ms "
                         f">= {critical_jitter_threshold:.2f}ms")
            return False
        
        if in_cooldown:
            remaining_cooldown = self.config.COOLDOWN_PERIOD_SEC - time_since_change
            logger.debug(f"In cooldown period, {remaining_cooldown:.1f}s remaining")
            
        return in_cooldown
    
    def determine_bandwidth_action(self, jitter: float, latency: float) -> Tuple[str, int]:
        """
        Intelligent bandwidth adjustment based on jitter vs latency analysis.
        
        Logic:
        - High Jitter -> Congestion detected -> Aggressive throttling
        - High Latency but Low Jitter -> Distance/Processing issue -> Gentle/No throttling
        - Both low -> Increase bandwidth
        
        Args:
            jitter: Smoothed jitter measurement in ms
            latency: Smoothed P95 latency measurement in ms
            
        Returns:
            Tuple[str, int]: (action_description, bandwidth_change_mbps)
        """
        high_jitter = jitter > self.config.TARGET_JITTER_MS
        high_latency = latency > self.config.TARGET_LATENCY_MS
        
        if high_jitter:
            # Jitter indicates congestion - throttle aggressively
            change = -self.config.AGGRESSIVE_DECREASE_MBPS
            action = f"CONGESTION_THROTTLE (Jitter: {jitter:.2f}ms)"
            
        elif high_latency and not high_jitter:
            # High latency but low jitter suggests distance/processing, not congestion
            # Throttle gently or not at all
            change = -self.config.GENTLE_DECREASE_MBPS
            action = f"LATENCY_GENTLE_THROTTLE (P95: {latency:.2f}ms, Jitter: {jitter:.2f}ms)"
            
        elif not high_jitter and not high_latency:
            # Both metrics good - can increase bandwidth if not in cooldown
            if not self.should_respect_cooldown(jitter):
                change = self.config.INCREASE_STEP_MBPS
                action = f"INCREASE (Good metrics: J={jitter:.2f}ms, P95={latency:.2f}ms)"
            else:
                change = 0
                action = f"COOLDOWN_WAIT (Good metrics but respecting cooldown)"
                
        else:
            # Edge case - maintain current bandwidth
            change = 0
            action = f"MAINTAIN (J={jitter:.2f}ms, P95={latency:.2f}ms)"
        
        return action, change
    
    def adjust_bandwidth(self, jitter: float, latency: float) -> Tuple[int, str]:
        """
        Calculate new bandwidth based on jitter and latency with hysteresis control.
        
        Args:
            jitter: Smoothed jitter measurement in ms
            latency: Smoothed P95 latency measurement in ms
            
        Returns:
            Tuple[int, str]: (new_bandwidth_mbps, action_description)
        """
        action_desc, bandwidth_change = self.determine_bandwidth_action(jitter, latency)
        
        new_bandwidth = self.current_bandwidth + bandwidth_change
        
        # Ensure bandwidth stays within bounds
        new_bandwidth = max(
            self.config.MIN_BANDWIDTH_MBPS,
            min(new_bandwidth, self.config.MAX_BANDWIDTH_MBPS)
        )
        
        # Track change direction for hysteresis
        if bandwidth_change > 0:
            self.last_bandwidth_change = 1  # Increase
        elif bandwidth_change < 0:
            self.last_bandwidth_change = -1  # Decrease
        else:
            self.last_bandwidth_change = 0  # No change
        
        return new_bandwidth, action_desc

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
                name=self.config.DEPLOYMENT_NAME,
                namespace=self.config.NAMESPACE
            )
            
            # Ensure metadata and annotations exist
            if deployment.spec.template.metadata is None:
                deployment.spec.template.metadata = client.V1ObjectMeta()
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}
            
            # Update bandwidth annotation
            deployment.spec.template.metadata.annotations[
                self.config.BANDWIDTH_ANNOTATION
            ] = f"{bandwidth_mbps}M"
            
            # Apply the update
            self.k8s_client.patch_namespaced_deployment(
                name=self.config.DEPLOYMENT_NAME,
                namespace=self.config.NAMESPACE,
                body=deployment
            )
            
            # Update hysteresis timestamp
            self.last_change_time = time.time()
            
            logger.info(f"Updated bandwidth limit to {bandwidth_mbps}Mbps")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update deployment: {e}")
            return False
    
    def run(self):
        """
        Main control loop with production-grade features:
        - True IQR-based jitter calculation from real Hubble metrics
        - EWMA signal smoothing 
        - Hysteresis for stability
        
        Requires real Hubble metrics - no synthetic fallbacks in production.
        """
        logger.info("Production ML Controller started...")
        logger.info("Features: IQR Jitter + EWMA Smoothing + Hysteresis")
        logger.info("Requirements: Real Hubble latency metrics (no synthetic fallbacks)")
        
        try:
            while True:
                try:
                    # Get raw metrics from Prometheus/Hubble (production requirement)
                    raw_jitter, raw_latency = self.metrics.get_latency_metrics()
                    
                    # Apply EWMA smoothing to reduce noise
                    smoothed_jitter, smoothed_latency = self.apply_ewma_smoothing(
                        raw_jitter, raw_latency
                    )
                    
                    logger.info(f"Metrics - Raw: J={raw_jitter:.2f}ms/P95={raw_latency:.2f}ms, "
                               f"Smoothed: J={smoothed_jitter:.2f}ms/P95={smoothed_latency:.2f}ms")
                    
                    # Calculate new bandwidth with intelligent logic
                    new_bandwidth, action_desc = self.adjust_bandwidth(
                        smoothed_jitter, smoothed_latency
                    )
                    
                    # Apply bandwidth change if it exceeds threshold
                    bandwidth_change = abs(new_bandwidth - self.current_bandwidth)
                    if bandwidth_change >= self.config.UPDATE_THRESHOLD_MBPS:
                        logger.info(f"Action: {action_desc}")
                        logger.info(f"Bandwidth change: {self.current_bandwidth}Mbps -> {new_bandwidth}Mbps")
                        
                        if self.update_deployment_bandwidth(new_bandwidth):
                            self.current_bandwidth = new_bandwidth
                    else:
                        logger.info(f"Action: {action_desc} (No update - change too small: {bandwidth_change}Mbps)")
                
                except RuntimeError as e:
                    # Real metrics not available - this is a production failure
                    logger.error(f"Production metrics failure: {e}")
                    logger.error("Controller cannot operate without real Hubble metrics")
                    logger.info(f"Waiting {METRICS_UNAVAILABLE_RETRY_DELAY} seconds before retry...")
                    time.sleep(METRICS_UNAVAILABLE_RETRY_DELAY)
                    continue
                
                # Wait before next control iteration
                time.sleep(self.config.CONTROL_INTERVAL_SEC)
                
        except KeyboardInterrupt:
            logger.info("Production ML Controller stopped by user")
        except Exception as e:
            logger.error(f"Unexpected error in control loop: {e}")
            raise

def main():
    """Entry point for the controller: instantiate and run the BandwidthController."""
    # Allow overriding config file path via environment variable
    config_file = os.getenv('ML_CONTROLLER_CONFIG_FILE', None)
    controller = BandwidthController(config_file)
    controller.run()


if __name__ == "__main__":
    main()
