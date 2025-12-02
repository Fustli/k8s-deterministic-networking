#!/usr/bin/env python3
"""
Critical Application SLA Configuration Loader
Parses critical-apps.yaml and provides config to flow_manager
"""

import yaml
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CriticalAppConfig:
    """Configuration for a single critical application"""
    name: str
    service: str
    port: int
    protocol: str
    max_jitter_ms: float
    max_latency_ms: Optional[float]
    priority: int


@dataclass
class BestEffortTarget:
    """Best-effort deployment to throttle"""
    deployment: str
    namespace: str
    initial_bandwidth: int


@dataclass
class ControlConfig:
    """Global control parameters"""
    probe_interval: float
    control_interval: float
    window_size: int
    step_down: int
    step_up: int
    min_bandwidth: int
    max_bandwidth: int


@dataclass
class SystemConfig:
    """Complete system configuration"""
    control: ControlConfig
    critical_apps: List[CriticalAppConfig]
    best_effort_targets: List[BestEffortTarget]
    aggregation_method: str
    severity_multiplier_enabled: bool
    severity_max_multiplier: float


class ConfigLoader:
    """Loads and validates critical-apps.yaml configuration"""
    
    @staticmethod
    def load(config_path: str = "/etc/flowmanager/critical-apps.yaml") -> SystemConfig:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded configuration from {config_path}")
            return ConfigLoader._parse_config(config)
            
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            raise
    
    @staticmethod
    def _parse_config(config: dict) -> SystemConfig:
        """Parse and validate configuration dictionary"""
        
        # Parse control parameters
        ctrl = config['control']
        control_config = ControlConfig(
            probe_interval=float(ctrl['probe_interval']),
            control_interval=float(ctrl['control_interval']),
            window_size=int(ctrl['window_size']),
            step_down=int(ctrl['step_down']),
            step_up=int(ctrl['step_up']),
            min_bandwidth=int(ctrl['min_bandwidth']),
            max_bandwidth=int(ctrl['max_bandwidth'])
        )
        
        # Parse critical applications
        critical_apps = []
        for app in config['critical_apps']:
            critical_apps.append(CriticalAppConfig(
                name=app['name'],
                service=app['service'],
                port=int(app['port']),
                protocol=app['protocol'],
                max_jitter_ms=float(app['max_jitter_ms']),
                max_latency_ms=app.get('max_latency_ms'),
                priority=int(app['priority'])
            ))
        
        # Sort by priority (highest first)
        critical_apps.sort(key=lambda x: x.priority, reverse=True)
        
        # Parse best-effort targets
        best_effort = []
        for target in config['best_effort_targets']:
            best_effort.append(BestEffortTarget(
                deployment=target['deployment'],
                namespace=target['namespace'],
                initial_bandwidth=int(target['initial_bandwidth'])
            ))
        
        # Parse aggregation settings (optional, use defaults if not provided)
        severity_enabled = config.get('severity_multiplier_enabled', True)
        severity_max = config.get('severity_max_multiplier', 5.0)
        
        return SystemConfig(
            control=control_config,
            critical_apps=critical_apps,
            best_effort_targets=best_effort,
            aggregation_method='priority',  # Always use priority-based
            severity_multiplier_enabled=severity_enabled,
            severity_max_multiplier=float(severity_max)
        )
    
    @staticmethod
    def validate(config: SystemConfig) -> bool:
        """Validate configuration consistency"""
        
        # Check at least one critical app defined
        if not config.critical_apps:
            logger.error("No critical applications defined")
            return False
        
        # Check at least one best-effort target
        if not config.best_effort_targets:
            logger.error("No best-effort targets defined")
            return False
        
        # Validate bandwidth ranges
        if config.control.min_bandwidth >= config.control.max_bandwidth:
            logger.error("min_bandwidth must be < max_bandwidth")
            return False
        
        # Validate protocols
        valid_protocols = ['TCP', 'UDP']
        for app in config.critical_apps:
            if app.protocol not in valid_protocols:
                logger.error(f"Invalid protocol {app.protocol} for {app.name}")
                return False
        
        logger.info("Configuration validation passed")
        return True
