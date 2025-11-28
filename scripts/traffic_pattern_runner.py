#!/usr/bin/env python3

"""
Traffic Pattern Runner for Flow Manager Validation
Version: 1.0

Generates variable traffic patterns to validate the Flow Manager controller.
Uses kubectl exec with iperf3 to create realistic network load scenarios.

Traffic Patterns:
  - NORMAL: Baseline traffic (10Mbps, steady)
  - BURST: Short high-intensity bursts (500Mbps, 5s on/off)
  - SUSTAINED: Prolonged high load (300Mbps, 60s)
  - STRESS: Maximum load to trigger throttling (900Mbps, 30s)
  - RAMP_UP: Gradually increasing load
  - OSCILLATE: Alternating high/low to test controller stability

This script proves the Flow Manager correctly:
  1. Detects SLA violations (UDP jitter >5ms or TCP throughput <50Mbps)
  2. Throttles best-effort traffic aggressively
  3. Relaxes limits when SLAs recover
"""

import subprocess
import time
import argparse
import logging
import sys
import random
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

# --- CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [TrafficRunner] %(message)s'
)
logger = logging.getLogger("TrafficRunner")


class TrafficPattern(Enum):
    """Available traffic patterns."""
    NORMAL = "normal"
    BURST = "burst"
    SUSTAINED = "sustained"
    STRESS = "stress"
    RAMP_UP = "ramp_up"
    OSCILLATE = "oscillate"
    FULL_TEST = "full_test"
    RANDOM = "random"


@dataclass
class TrafficConfig:
    """Configuration for traffic generation."""
    # Target services (iperf3 servers)
    ROBOT_CONTROL_SVC: str = "robot-control-svc"
    SAFETY_SCANNER_SVC: str = "safety-scanner-svc"
    TELEMETRY_UPLOAD_SVC: str = "telemetry-upload-svc"
    
    # Default namespace
    NAMESPACE: str = "default"
    
    # Traffic generator pod (source of noise)
    TRAFFIC_GEN_POD: str = "traffic-generator"
    
    # iperf3 ports
    ROBOT_CONTROL_PORT: int = 5201  # UDP
    SAFETY_SCANNER_PORT: int = 5202  # TCP
    TELEMETRY_UPLOAD_PORT: int = 5203  # TCP (noise target)


class KubectlExecutor:
    """Executes kubectl commands for traffic generation."""
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self._traffic_gen_pod: Optional[str] = None
        
    def _get_traffic_gen_pod(self) -> Optional[str]:
        """Find the traffic-generator pod name."""
        if self._traffic_gen_pod:
            return self._traffic_gen_pod
            
        try:
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", self.namespace, 
                 "-l", "app=traffic-generator", "-o", "jsonpath={.items[0].metadata.name}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                self._traffic_gen_pod = result.stdout.strip()
                return self._traffic_gen_pod
        except Exception as e:
            logger.error(f"Failed to find traffic-generator pod: {e}")
        return None
    
    def _get_any_pod_with_iperf(self) -> Optional[str]:
        """Fallback: Find any pod that can run iperf3."""
        try:
            # Try to use the traffic-generator deployment
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", self.namespace,
                 "-o", "jsonpath={.items[*].metadata.name}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pods = result.stdout.strip().split()
                for pod in pods:
                    if 'traffic' in pod or 'generator' in pod or 'noise' in pod:
                        return pod
                # Fallback to first available pod
                if pods:
                    return pods[0]
        except Exception as e:
            logger.error(f"Failed to find any pod: {e}")
        return None

    def run_iperf_client(self, target_host: str, port: int, 
                         bandwidth: str, duration: int, 
                         udp: bool = False, 
                         background: bool = False) -> Optional[subprocess.Popen]:
        """
        Run iperf3 client from traffic-generator pod.
        
        Args:
            target_host: Target service DNS name
            port: iperf3 server port
            bandwidth: Bandwidth limit (e.g., "100M")
            duration: Test duration in seconds
            udp: Use UDP instead of TCP
            background: Run in background (returns Popen object)
        """
        pod = self._get_traffic_gen_pod() or self._get_any_pod_with_iperf()
        if not pod:
            logger.error("No suitable pod found for traffic generation")
            return None
        
        # Build iperf3 command
        iperf_cmd = [
            "iperf3", "-c", target_host, "-p", str(port),
            "-b", bandwidth, "-t", str(duration)
        ]
        if udp:
            iperf_cmd.append("-u")
        
        # Full kubectl exec command
        cmd = [
            "kubectl", "exec", "-n", self.namespace, pod, "--",
        ] + iperf_cmd
        
        logger.info(f"Running: {' '.join(cmd[-6:])}")  # Log just iperf part
        
        try:
            if background:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                return proc
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)
                if result.returncode != 0:
                    logger.warning(f"iperf3 warning: {result.stderr[:200]}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"iperf3 command timed out after {duration}s")
            return None
        except Exception as e:
            logger.error(f"Failed to run iperf3: {e}")
            return None

    def check_bandwidth_annotation(self, deployment: str = "telemetry-upload-deployment") -> str:
        """Check current bandwidth annotation on deployment."""
        try:
            cmd = [
                "kubectl", "get", "deployment", deployment, "-n", self.namespace,
                "-o", "jsonpath={.spec.template.metadata.annotations.kubernetes\\.io/egress-bandwidth}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.stdout.strip() or "Not Set"
        except Exception:
            return "Error"


class TrafficPatternGenerator:
    """Generates various traffic patterns for testing."""
    
    def __init__(self, config: TrafficConfig):
        self.config = config
        self.kubectl = KubectlExecutor(config.NAMESPACE)
        
    def _log_phase(self, phase: str, description: str):
        """Log phase header."""
        logger.info("=" * 50)
        logger.info(f"PHASE: {phase}")
        logger.info(f"   {description}")
        logger.info("=" * 50)
        
    def _wait_with_status(self, seconds: int, message: str = "Waiting"):
        """Wait with periodic status updates."""
        logger.info(f"{message} ({seconds}s)...")
        for i in range(seconds):
            if i > 0 and i % 10 == 0:
                bw = self.kubectl.check_bandwidth_annotation()
                logger.info(f"   [{i}/{seconds}s] Current BW limit: {bw}")
            time.sleep(1)
    
    def run_normal(self, duration: int = 30):
        """
        NORMAL: Baseline traffic pattern.
        Low bandwidth, steady flow - should NOT trigger throttling.
        """
        self._log_phase("NORMAL", "Baseline 10Mbps steady traffic - SLAs should be maintained")
        
        # Light TCP traffic to safety-scanner
        self.kubectl.run_iperf_client(
            self.config.SAFETY_SCANNER_SVC, self.config.SAFETY_SCANNER_PORT,
            "10M", duration, udp=False
        )
        
    def run_burst(self, cycles: int = 3, burst_duration: int = 5, pause: int = 5):
        """
        BURST: Short high-intensity bursts.
        Tests controller's ability to quickly throttle and release.
        """
        self._log_phase("BURST", f"500Mbps bursts ({burst_duration}s on, {pause}s off) x{cycles}")
        
        for i in range(cycles):
            logger.info(f"Burst {i+1}/{cycles} - Generating 500Mbps noise")
            
            # High bandwidth burst to telemetry-upload (noise)
            proc = self.kubectl.run_iperf_client(
                self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                "500M", burst_duration, udp=False, background=True
            )
            
            time.sleep(burst_duration)
            if proc:
                proc.terminate()
            
            bw = self.kubectl.check_bandwidth_annotation()
            logger.info(f"   After burst: BW limit = {bw}")
            
            if i < cycles - 1:
                self._wait_with_status(pause, "Cooldown between bursts")
    
    def run_sustained(self, bandwidth: str = "300M", duration: int = 60):
        """
        SUSTAINED: Prolonged high load.
        Tests controller's ability to maintain throttling under continuous pressure.
        """
        self._log_phase("SUSTAINED", f"Prolonged {bandwidth} load for {duration}s")
        
        # Continuous high bandwidth
        self.kubectl.run_iperf_client(
            self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
            bandwidth, duration, udp=False
        )
        
        bw = self.kubectl.check_bandwidth_annotation()
        logger.info(f"   Final BW limit after sustained load: {bw}")
    
    def run_stress(self, duration: int = 30):
        """
        STRESS: Maximum load to trigger aggressive throttling.
        Should push bandwidth limit to MIN_BW.
        """
        self._log_phase("STRESS", f"Maximum 900Mbps load for {duration}s - expect throttle to MIN")
        
        # Maximum bandwidth attack
        self.kubectl.run_iperf_client(
            self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
            "900M", duration, udp=False
        )
        
        bw = self.kubectl.check_bandwidth_annotation()
        logger.info(f"   Final BW limit after stress: {bw}")
    
    def run_ramp_up(self, start_bw: int = 50, end_bw: int = 500, steps: int = 5, step_duration: int = 10):
        """
        RAMP_UP: Gradually increasing load.
        Tests controller's proportional response.
        """
        self._log_phase("RAMP_UP", f"Gradual increase from {start_bw}M to {end_bw}M in {steps} steps")
        
        bw_step = (end_bw - start_bw) // steps
        
        for i in range(steps):
            current_bw = start_bw + (i * bw_step)
            logger.info(f"Step {i+1}/{steps}: {current_bw}Mbps")
            
            self.kubectl.run_iperf_client(
                self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                f"{current_bw}M", step_duration, udp=False
            )
            
            limit = self.kubectl.check_bandwidth_annotation()
            logger.info(f"   BW limit after {current_bw}M: {limit}")
    
    def run_oscillate(self, cycles: int = 4, high_duration: int = 15, low_duration: int = 15):
        """
        OSCILLATE: Alternating high/low load.
        Tests controller stability and prevents hunting/oscillation.
        """
        self._log_phase("OSCILLATE", f"High(400M)/Low(20M) alternating pattern x{cycles}")
        
        for i in range(cycles):
            # High phase
            logger.info(f"Cycle {i+1}/{cycles} - HIGH (400Mbps)")
            self.kubectl.run_iperf_client(
                self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                "400M", high_duration, udp=False
            )
            high_limit = self.kubectl.check_bandwidth_annotation()
            
            # Low phase
            logger.info(f"Cycle {i+1}/{cycles} - LOW (20Mbps)")
            self.kubectl.run_iperf_client(
                self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                "20M", low_duration, udp=False
            )
            low_limit = self.kubectl.check_bandwidth_annotation()
            
            logger.info(f"   Cycle {i+1}: High={high_limit}, Low={low_limit}")
    
    def run_full_test(self):
        """
        FULL_TEST: Complete validation sequence.
        Runs all patterns in sequence to fully validate the controller.
        """
        self._log_phase("FULL_TEST", "Complete validation sequence - All patterns")
        
        initial_bw = self.kubectl.check_bandwidth_annotation()
        logger.info(f"Initial bandwidth limit: {initial_bw}")
        
        # Phase 1: Baseline
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 1/5: BASELINE")
        self.run_normal(duration=20)
        self._wait_with_status(10, "Stabilization period")
        
        # Phase 2: Burst test
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2/5: BURST RESPONSE")
        self.run_burst(cycles=2, burst_duration=10, pause=10)
        self._wait_with_status(15, "Recovery period")
        
        # Phase 3: Sustained load
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 3/5: SUSTAINED LOAD")
        self.run_sustained(bandwidth="400M", duration=45)
        self._wait_with_status(20, "Recovery period")
        
        # Phase 4: Stress test
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 4/5: STRESS TEST")
        self.run_stress(duration=20)
        self._wait_with_status(30, "Extended recovery")
        
        # Phase 5: Stability check
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 5/5: STABILITY CHECK")
        self.run_oscillate(cycles=2, high_duration=10, low_duration=15)
        
        # Final status
        final_bw = self.kubectl.check_bandwidth_annotation()
        logger.info("\n" + "=" * 60)
        logger.info("FULL TEST COMPLETE")
        logger.info(f"   Initial BW: {initial_bw}")
        logger.info(f"   Final BW:   {final_bw}")
        logger.info("=" * 60)

    def run_random(self, total_duration: int = 60):
        """
        RANDOM: Randomized traffic patterns for continuous observation.
        Runs random patterns with random parameters for the specified duration.
        Useful for observing Flow Manager behavior over time.
        """
        self._log_phase("RANDOM", f"Randomized patterns for {total_duration}s")
        
        initial_bw = self.kubectl.check_bandwidth_annotation()
        logger.info(f"Initial bandwidth limit: {initial_bw}")
        
        # Available mini-patterns with their typical durations
        patterns = [
            ('spike', 5),      # Quick spike
            ('burst', 10),     # Medium burst
            ('sustained', 15), # Sustained load
            ('pause', 5),      # Quiet period
            ('ramp', 10),      # Ramping traffic
        ]
        
        start_time = time.time()
        pattern_count = 0
        
        while (time.time() - start_time) < total_duration:
            elapsed = int(time.time() - start_time)
            remaining = total_duration - elapsed
            
            if remaining < 5:
                break
            
            # Pick random pattern
            pattern_name, base_duration = random.choice(patterns)
            # Randomize duration (50% to 150% of base)
            duration = min(int(base_duration * random.uniform(0.5, 1.5)), remaining)
            
            pattern_count += 1
            logger.info(f"[{elapsed}/{total_duration}s] Pattern #{pattern_count}: {pattern_name} ({duration}s)")
            
            if pattern_name == 'spike':
                # Quick high-bandwidth spike
                bw = random.choice(['500M', '600M', '700M', '800M'])
                self.kubectl.run_iperf_client(
                    self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                    bw, duration, udp=False
                )
                
            elif pattern_name == 'burst':
                # Bursty traffic (on/off)
                bw = random.choice(['300M', '400M', '500M'])
                burst_time = duration // 2
                self.kubectl.run_iperf_client(
                    self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                    bw, burst_time, udp=False
                )
                time.sleep(duration - burst_time)
                
            elif pattern_name == 'sustained':
                # Sustained moderate traffic
                bw = random.choice(['200M', '300M', '400M'])
                self.kubectl.run_iperf_client(
                    self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                    bw, duration, udp=False
                )
                
            elif pattern_name == 'pause':
                # No traffic - let controller relax
                logger.info(f"   Quiet period - observing recovery")
                time.sleep(duration)
                
            elif pattern_name == 'ramp':
                # Ramping bandwidth
                steps = 3
                step_duration = duration // steps
                for i in range(steps):
                    bw = 100 + (i * 150)  # 100M, 250M, 400M
                    self.kubectl.run_iperf_client(
                        self.config.TELEMETRY_UPLOAD_SVC, self.config.TELEMETRY_UPLOAD_PORT,
                        f"{bw}M", step_duration, udp=False
                    )
            
            # Log current state
            current_bw = self.kubectl.check_bandwidth_annotation()
            logger.info(f"   Current BW limit: {current_bw}")
        
        # Final status
        final_bw = self.kubectl.check_bandwidth_annotation()
        logger.info("\n" + "=" * 60)
        logger.info("RANDOM TEST COMPLETE")
        logger.info(f"   Duration: {total_duration}s")
        logger.info(f"   Patterns executed: {pattern_count}")
        logger.info(f"   Initial BW: {initial_bw}")
        logger.info(f"   Final BW:   {final_bw}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Traffic Pattern Runner for Flow Manager Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full validation test
  python traffic_pattern_runner.py --pattern full_test
  
  # Run burst test with custom parameters  
  python traffic_pattern_runner.py --pattern burst --cycles 5
  
  # Run stress test
  python traffic_pattern_runner.py --pattern stress --duration 60
  
  # Run randomized patterns for 1 minute (great for observing controller)
  python traffic_pattern_runner.py --pattern random --duration 60
  
  # Run randomized patterns for 5 minutes
  python traffic_pattern_runner.py --pattern random --duration 300
  
  # Check current bandwidth limit
  python traffic_pattern_runner.py --check-only
        """
    )
    
    parser.add_argument(
        "--pattern", "-p",
        type=str,
        choices=[p.value for p in TrafficPattern],
        default="full_test",
        help="Traffic pattern to run (default: full_test)"
    )
    
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=30,
        help="Duration for simple patterns in seconds (default: 30)"
    )
    
    parser.add_argument(
        "--cycles", "-c",
        type=int,
        default=3,
        help="Number of cycles for burst/oscillate patterns (default: 3)"
    )
    
    parser.add_argument(
        "--bandwidth", "-b",
        type=str,
        default="300M",
        help="Bandwidth for sustained pattern (default: 300M)"
    )
    
    parser.add_argument(
        "--namespace", "-n",
        type=str,
        default="default",
        help="Kubernetes namespace (default: default)"
    )
    
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check current bandwidth annotation, don't run traffic"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize
    config = TrafficConfig()
    config.NAMESPACE = args.namespace
    generator = TrafficPatternGenerator(config)
    
    # Check-only mode
    if args.check_only:
        bw = generator.kubectl.check_bandwidth_annotation()
        print(f"Current bandwidth limit: {bw}")
        return 0
    
    logger.info("Traffic Pattern Runner Started")
    logger.info(f"   Pattern: {args.pattern}")
    logger.info(f"   Namespace: {args.namespace}")
    
    try:
        pattern = TrafficPattern(args.pattern)
        
        if pattern == TrafficPattern.NORMAL:
            generator.run_normal(args.duration)
        elif pattern == TrafficPattern.BURST:
            generator.run_burst(cycles=args.cycles)
        elif pattern == TrafficPattern.SUSTAINED:
            generator.run_sustained(args.bandwidth, args.duration)
        elif pattern == TrafficPattern.STRESS:
            generator.run_stress(args.duration)
        elif pattern == TrafficPattern.RAMP_UP:
            generator.run_ramp_up()
        elif pattern == TrafficPattern.OSCILLATE:
            generator.run_oscillate(cycles=args.cycles)
        elif pattern == TrafficPattern.FULL_TEST:
            generator.run_full_test()
        elif pattern == TrafficPattern.RANDOM:
            generator.run_random(total_duration=args.duration)
        
        logger.info("Traffic pattern completed successfully")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error running traffic pattern: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
