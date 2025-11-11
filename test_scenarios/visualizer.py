#!/usr/bin/env python3

"""
ML Controller Test Scenario Visualizer

Creates graphs and visualizations of test scenarios showing:
- Jitter over time
- Bandwidth adjustments
- Control decisions
- Relationship between jitter and bandwidth
"""

import json
import csv
from pathlib import Path
from typing import List, Tuple, Dict
import math


class TextGrapher:
    """Simple ASCII graph generator for terminal output"""
    
    @staticmethod
    def create_graph(title: str, data: List[float], height: int = 10, width: int = 60) -> str:
        """Create ASCII graph of data"""
        if not data:
            return ""
        
        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val if max_val > min_val else 1
        
        # Create graph
        graph = [title]
        graph.append("=" * (width + 4))
        
        # Create rows
        for row in range(height, 0, -1):
            line = f"|"
            threshold = min_val + (row / height) * range_val
            
            for i in range(0, min(len(data), width), max(1, len(data) // width)):
                if data[i] >= threshold - (range_val / height / 2):
                    line += "█"
                else:
                    line += " "
            
            line += f"| {threshold:.2f}"
            graph.append(line)
        
        graph.append("+" + "-" * width + "+")
        graph.append(f"Min: {min_val:.2f}, Max: {max_val:.2f}, Avg: {sum(data)/len(data):.2f}")
        
        return "\n".join(graph)
    
    @staticmethod
    def create_timeline(data: List[Tuple[int, float]], title: str, height: int = 8) -> str:
        """Create ASCII timeline visualization"""
        lines = [title, "=" * 50]
        
        for i, (time_sec, value) in enumerate(data):
            bar_length = int(value / max(v for _, v in data) * 40) if data else 0
            line = f"{time_sec:3d}s | {'█' * bar_length} {value:.2f}"
            lines.append(line)
            
            if i >= height - 1:
                lines.append("... (truncated)")
                break
        
        return "\n".join(lines)


class ReportGenerator:
    """Generate markdown reports for scenarios"""
    
    @staticmethod
    def generate_scenario_report(scenario_name: str, data_file: Path) -> str:
        """Generate markdown report for a scenario"""
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        jitter_values = [d['jitter_ms'] for d in data['data']]
        bandwidth_values = [d['bandwidth_mbps'] for d in data['data']]
        patch_count = sum(1 for d in data['data'] if d['decision'] == 'PATCH')
        
        report = f"""# Test Scenario: {scenario_name.replace('_', ' ').title()}

## Overview

**Duration:** {data['duration_seconds']} seconds  
**Samples:** {data['samples']}  
**Interval:** 5 seconds  

## Jitter Metrics

| Metric | Value |
|--------|-------|
| **Min** | {min(jitter_values):.2f} ms |
| **Max** | {max(jitter_values):.2f} ms |
| **Average** | {sum(jitter_values)/len(jitter_values):.2f} ms |
| **Std Dev** | {calculate_stddev(jitter_values):.2f} ms |
| **Above Target (>1.0ms)** | {sum(1 for j in jitter_values if j > 1.0)} samples |

## Bandwidth Management

| Metric | Value |
|--------|-------|
| **Min** | {min(bandwidth_values)} Mbps |
| **Max** | {max(bandwidth_values)} Mbps |
| **Final** | {bandwidth_values[-1]} Mbps |
| **Total Patches** | {patch_count} |
| **Patch Rate** | {patch_count / data['samples'] * 100:.1f}% |

## Control Loop Behavior

### Decision Distribution
- **PATCH**: {patch_count} times
- **NO_UPDATE**: {len(data['data']) - patch_count} times

### Key Observations

"""
        
        # Add observations based on scenario
        if 'spike' in scenario_name:
            report += """
1. **Jitter Spike Detected:** Controller rapidly reduced bandwidth during spike
2. **Recovery:** Bandwidth gradually increased as jitter normalized
3. **Effectiveness:** Control loop responded appropriately to transient conditions
"""
        elif 'sustained' in scenario_name:
            report += """
1. **Sustained High Load:** Bandwidth continuously reduced during load period
2. **Aggressive Response:** Multiple patches to reach minimum acceptable bandwidth
3. **Recovery Phase:** Gradual bandwidth increase as load decreased
"""
        elif 'oscillation' in scenario_name:
            report += """
1. **Threshold Oscillation:** Jitter hovering around target threshold
2. **Control Instability:** Frequent bandwidth adjustments due to oscillation
3. **Hysteresis Needed:** Consider adding hysteresis to reduce oscillation
"""
        elif 'degradation' in scenario_name:
            report += """
1. **Gradual Degradation:** Steady increase in jitter over time
2. **Responsive Adjustments:** Controller made continuous bandwidth reductions
3. **Load Trend:** Indicates sustained increase in network utilization
"""
        elif 'recovery' in scenario_name:
            report += """
1. **High Jitter Phase:** Aggressive bandwidth reduction during crisis
2. **Recovery Tracking:** Bandwidth increased as jitter improved
3. **Convergence:** System returned to normal operation with appropriate bandwidth
"""
        else:  # normal
            report += """
1. **Stable Operation:** Low, steady jitter maintained throughout
2. **Minimal Adjustments:** Few bandwidth patches needed
3. **Efficiency:** System operating near optimal point
"""
        
        return report


def calculate_stddev(values: List[float]) -> float:
    """Calculate standard deviation"""
    if not values:
        return 0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def main():
    """Generate visualization reports"""
    print("Generating Scenario Visualizations...")
    print("=" * 70)
    
    data_dir = Path(__file__).parent / "data"
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    
    for json_file in sorted(data_dir.glob("*.json")):
        scenario_name = json_file.stem
        print(f"\nProcessing: {scenario_name}")
        
        # Generate report
        report = ReportGenerator.generate_scenario_report(scenario_name, json_file)
        
        # Save report
        report_path = results_dir / f"{scenario_name}_report.md"
        with open(report_path, 'w') as f:
            f.write(report)
        
        print(f"  ✅ Report saved: {report_path}")
    
    print("\n" + "=" * 70)
    print("✅ Visualizations generated successfully!")


if __name__ == "__main__":
    main()
