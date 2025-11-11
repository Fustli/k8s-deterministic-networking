#!/usr/bin/env python3

"""
ML Controller Test Scenario Simulator

Simulates various network conditions and generates data that the ML controller
would receive from Prometheus/Hubble. Useful for testing control loop behavior
without needing a live cluster.

Scenarios:
- Normal operation: steady low jitter
- Jitter spike: sudden increase then recovery
- Sustained high load: prolonged high jitter
- Oscillation: jitter bounces around threshold
- Degradation: gradually increasing jitter
- Recovery: high jitter returning to normal
"""

import json
import csv
from pathlib import Path
from typing import List, Tuple
import math


class JitterGenerator:
    """Generate jitter data for different network scenarios"""
    
    def __init__(self, duration_seconds: int = 300, interval_seconds: int = 5):
        """
        Initialize jitter generator.
        
        Args:
            duration_seconds: Total duration of simulation
            interval_seconds: Time between measurements
        """
        self.duration = duration_seconds
        self.interval = interval_seconds
        self.num_samples = duration_seconds // interval_seconds
        self.target_jitter = 1.0  # ms
        
    def generate_normal_operation(self) -> List[float]:
        """Low, steady jitter with minor fluctuations"""
        jitter = []
        for i in range(self.num_samples):
            # Base jitter around 0.3ms with small noise
            base = 0.3
            noise = (i % 5) * 0.02  # Gentle fluctuation
            value = base + noise
            jitter.append(round(value, 2))
        return jitter
    
    def generate_jitter_spike(self) -> List[float]:
        """Sudden spike then recovery"""
        jitter = []
        spike_start = 80  # At 400 seconds
        spike_duration = 40  # 200 seconds duration
        
        for i in range(self.num_samples):
            if spike_start <= i < spike_start + spike_duration:
                # Gaussian spike centered at spike_start + duration/2
                center = spike_start + spike_duration / 2
                sigma = spike_duration / 4
                spike_magnitude = 5.0 * math.exp(-((i - center) ** 2) / (2 * sigma ** 2))
                value = 0.3 + spike_magnitude
            else:
                # Normal operation
                value = 0.3 + (i % 5) * 0.02
            
            jitter.append(round(value, 2))
        return jitter
    
    def generate_sustained_high_load(self) -> List[float]:
        """Prolonged high jitter from high load"""
        jitter = []
        for i in range(self.num_samples):
            # Ramp up, sustain, ramp down
            if i < 30:  # Ramp up
                value = 0.3 + (i / 30) * 4.5
            elif i < 150:  # Sustained high
                value = 4.8 + (i % 10) * 0.1
            else:  # Ramp down
                value = 4.8 - ((i - 150) / (self.num_samples - 150)) * 4.5
            
            jitter.append(round(max(0.1, value), 2))
        return jitter
    
    def generate_oscillation(self) -> List[float]:
        """Jitter oscillates around the target threshold"""
        jitter = []
        for i in range(self.num_samples):
            # Sine wave oscillating around target (1.0ms)
            oscillation = 0.7 * math.sin(i * 0.05)
            value = self.target_jitter + oscillation
            jitter.append(round(max(0.1, value), 2))
        return jitter
    
    def generate_degradation(self) -> List[float]:
        """Gradually increasing jitter over time"""
        jitter = []
        for i in range(self.num_samples):
            # Linear degradation
            degradation_rate = 0.01  # 0.01ms per interval
            base = 0.3
            value = base + (i * degradation_rate)
            
            # Add some noise
            noise = 0.1 * math.sin(i * 0.1)
            value = value + noise
            jitter.append(round(value, 2))
        return jitter
    
    def generate_recovery(self) -> List[float]:
        """High jitter recovering to normal"""
        jitter = []
        for i in range(self.num_samples):
            if i < 50:
                # High jitter phase
                value = 3.5 + (i % 10) * 0.2
            elif i < 150:
                # Recovery phase
                recovery_progress = (i - 50) / 100
                value = 3.5 * (1 - recovery_progress) + 0.3 * recovery_progress
            else:
                # Back to normal
                value = 0.3 + (i % 5) * 0.02
            
            jitter.append(round(value, 2))
        return jitter


class ControlLoopSimulator:
    """Simulate ML controller behavior with jitter data"""
    
    def __init__(self):
        self.target_jitter = 1.0
        self.min_bandwidth = 10
        self.max_bandwidth = 1000
        self.decrease_step = 50
        self.increase_step = 10
        self.update_threshold = 5
        self.current_bandwidth = 100
        
    def simulate(self, jitter_data: List[float]) -> Tuple[List[float], List[int], List[str]]:
        """
        Simulate control loop decisions for given jitter data.
        
        Returns:
            (jitter, bandwidth, decisions) - parallel arrays of simulation results
        """
        bandwidth_history = []
        decisions = []
        
        for jitter in jitter_data:
            # Calculate new bandwidth
            if jitter > self.target_jitter:
                new_bandwidth = self.current_bandwidth - self.decrease_step
            else:
                new_bandwidth = self.current_bandwidth + self.increase_step
            
            # Clamp to bounds
            new_bandwidth = max(self.min_bandwidth, min(new_bandwidth, self.max_bandwidth))
            
            # Check if change exceeds threshold
            if abs(new_bandwidth - self.current_bandwidth) >= self.update_threshold:
                self.current_bandwidth = new_bandwidth
                decision = "PATCH" if new_bandwidth < self.current_bandwidth else "PATCH"
            else:
                decision = "NO_UPDATE"
            
            bandwidth_history.append(self.current_bandwidth)
            decisions.append(decision)
        
        return jitter_data, bandwidth_history, decisions


def save_scenario_data(scenario_name: str, jitter: List[float], 
                       bandwidth: List[int], decisions: List[str],
                       output_dir: Path):
    """Save scenario data to CSV and JSON"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to CSV
    csv_path = output_dir / f"{scenario_name}.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_sec', 'jitter_ms', 'bandwidth_mbps', 'decision'])
        for i, (j, bw, d) in enumerate(zip(jitter, bandwidth, decisions)):
            writer.writerow([i * 5, j, bw, d])
    
    # Save to JSON
    json_path = output_dir / f"{scenario_name}.json"
    data = {
        'scenario': scenario_name,
        'duration_seconds': len(jitter) * 5,
        'samples': len(jitter),
        'data': [
            {
                'timestamp_sec': i * 5,
                'jitter_ms': j,
                'bandwidth_mbps': bw,
                'decision': d
            }
            for i, (j, bw, d) in enumerate(zip(jitter, bandwidth, decisions))
        ]
    }
    
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    return csv_path, json_path


def main():
    """Generate all test scenarios"""
    print("Generating ML Controller Test Scenarios...")
    print("=" * 70)
    
    scenarios_dir = Path(__file__).parent / "data"
    scenarios_dir.mkdir(exist_ok=True)
    
    generator = JitterGenerator(duration_seconds=300, interval_seconds=5)
    simulator = ControlLoopSimulator()
    
    scenarios = {
        "normal_operation": generator.generate_normal_operation,
        "jitter_spike": generator.generate_jitter_spike,
        "sustained_high_load": generator.generate_sustained_high_load,
        "oscillation": generator.generate_oscillation,
        "degradation": generator.generate_degradation,
        "recovery": generator.generate_recovery,
    }
    
    for scenario_name, generator_func in scenarios.items():
        print(f"\nGenerating: {scenario_name}")
        
        # Generate jitter data
        jitter_data = generator_func()
        
        # Simulate control loop
        simulator.current_bandwidth = 100  # Reset for each scenario
        jitter, bandwidth, decisions = simulator.simulate(jitter_data)
        
        # Save data
        csv_path, json_path = save_scenario_data(
            scenario_name, jitter, bandwidth, decisions, scenarios_dir
        )
        
        # Print statistics
        print(f"  Jitter - Min: {min(jitter):.2f}ms, Max: {max(jitter):.2f}ms, Avg: {sum(jitter)/len(jitter):.2f}ms")
        print(f"  Bandwidth - Min: {min(bandwidth)}Mbps, Max: {max(bandwidth)}Mbps, Final: {bandwidth[-1]}Mbps")
        print(f"  Patches made: {sum(1 for d in decisions if d == 'PATCH')}")
        print(f"  ✅ Saved: {csv_path}")
    
    print("\n" + "=" * 70)
    print("✅ All scenarios generated successfully!")


if __name__ == "__main__":
    main()
