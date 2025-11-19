#!/usr/bin/env python3
"""
Realistic Traffic Generator for K8s Deterministic Networking

Generates real-world traffic patterns to test the ML Controller and visualize
network behavior in Grafana. Simulates various production scenarios.
"""

import asyncio
import aiohttp
import time
import random
import logging
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TrafficPattern:
    """Defines a traffic generation pattern"""
    name: str
    description: str
    duration_seconds: int
    request_rate_per_second: int
    payload_size_kb: int
    concurrent_connections: int
    error_rate_percent: float = 0.0
    latency_variation_ms: int = 10

class RealisticTrafficGenerator:
    """Generate realistic traffic patterns for testing"""
    
    def __init__(self, target_service_url: str):
        self.target_url = target_service_url
        self.session = None
        self.metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'scenario_start_time': None
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def send_request(self, payload_size_kb: int, add_latency_ms: int = 0) -> Dict:
        """Send a single HTTP request with specified payload size"""
        start_time = time.time()
        
        # Generate payload of specified size
        payload = {'data': 'x' * (payload_size_kb * 1024), 'timestamp': time.time()}
        
        try:
            # Add artificial latency variation if specified
            if add_latency_ms > 0:
                await asyncio.sleep(add_latency_ms / 1000)
            
            async with self.session.post(
                f"{self.target_url}/api/process", 
                json=payload,
                headers={'Content-Type': 'application/json'}
            ) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    self.metrics['successful_requests'] += 1
                    return {
                        'status': 'success',
                        'response_time': response_time,
                        'status_code': response.status,
                        'payload_size': payload_size_kb
                    }
                else:
                    self.metrics['failed_requests'] += 1
                    return {
                        'status': 'error',
                        'response_time': response_time,
                        'status_code': response.status,
                        'error': f"HTTP {response.status}"
                    }
                    
        except Exception as e:
            self.metrics['failed_requests'] += 1
            response_time = time.time() - start_time
            return {
                'status': 'error',
                'response_time': response_time,
                'error': str(e)
            }
    
    async def run_traffic_pattern(self, pattern: TrafficPattern) -> Dict:
        """Execute a specific traffic pattern"""
        logger.info(f"Starting traffic pattern: {pattern.name}")
        logger.info(f"Description: {pattern.description}")
        logger.info(f"Duration: {pattern.duration_seconds}s, Rate: {pattern.request_rate_per_second} req/s")
        
        self.metrics['scenario_start_time'] = time.time()
        pattern_start = time.time()
        requests_sent = 0
        
        # Calculate request interval
        request_interval = 1.0 / pattern.request_rate_per_second
        
        while time.time() - pattern_start < pattern.duration_seconds:
            # Create batch of concurrent requests
            tasks = []
            
            for _ in range(pattern.concurrent_connections):
                # Add latency variation
                latency_variation = random.randint(0, pattern.latency_variation_ms)
                
                # Simulate errors based on error rate
                if random.random() < (pattern.error_rate_percent / 100):
                    # Skip this request to simulate network issues
                    continue
                
                task = self.send_request(pattern.payload_size_kb, latency_variation)
                tasks.append(task)
            
            # Execute requests concurrently
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                requests_sent += len(tasks)
                self.metrics['total_requests'] += len(tasks)
                
                # Log progress every 50 requests
                if requests_sent % 50 == 0:
                    elapsed = time.time() - pattern_start
                    current_rate = requests_sent / elapsed
                    logger.info(f"Pattern '{pattern.name}': {requests_sent} requests sent, "
                              f"current rate: {current_rate:.1f} req/s")
            
            # Wait for next batch
            await asyncio.sleep(request_interval)
        
        pattern_duration = time.time() - pattern_start
        actual_rate = requests_sent / pattern_duration
        
        logger.info(f"Completed pattern '{pattern.name}': {requests_sent} requests in {pattern_duration:.1f}s")
        logger.info(f"Actual rate: {actual_rate:.1f} req/s (target: {pattern.request_rate_per_second} req/s)")
        
        return {
            'pattern_name': pattern.name,
            'requests_sent': requests_sent,
            'duration': pattern_duration,
            'actual_rate': actual_rate,
            'target_rate': pattern.request_rate_per_second
        }

class ProductionScenarios:
    """Real-world production scenario definitions"""
    
    @staticmethod
    def get_scenarios() -> List[TrafficPattern]:
        """Return list of realistic production scenarios"""
        return [
            TrafficPattern(
                name="Morning Peak - E-commerce",
                description="Simulates morning shopping rush with high concurrent users",
                duration_seconds=300,  # 5 minutes
                request_rate_per_second=25,
                payload_size_kb=2,
                concurrent_connections=8,
                error_rate_percent=0.5,
                latency_variation_ms=50
            ),
            
            TrafficPattern(
                name="API Burst - Mobile App Sync",
                description="Mobile app synchronization creating traffic bursts",
                duration_seconds=180,  # 3 minutes
                request_rate_per_second=50,
                payload_size_kb=1,
                concurrent_connections=12,
                error_rate_percent=1.0,
                latency_variation_ms=100
            ),
            
            TrafficPattern(
                name="File Upload - Content Management",
                description="Users uploading files with varying sizes",
                duration_seconds=240,  # 4 minutes
                request_rate_per_second=10,
                payload_size_kb=50,  # Larger payloads
                concurrent_connections=5,
                error_rate_percent=2.0,
                latency_variation_ms=200
            ),
            
            TrafficPattern(
                name="Database Query Spike",
                description="Heavy database queries causing network congestion",
                duration_seconds=150,  # 2.5 minutes
                request_rate_per_second=40,
                payload_size_kb=5,
                concurrent_connections=15,
                error_rate_percent=3.0,
                latency_variation_ms=300
            ),
            
            TrafficPattern(
                name="Baseline - Normal Operations",
                description="Normal operational load for comparison",
                duration_seconds=360,  # 6 minutes
                request_rate_per_second=15,
                payload_size_kb=3,
                concurrent_connections=6,
                error_rate_percent=0.2,
                latency_variation_ms=25
            ),
            
            TrafficPattern(
                name="Microservice Communication",
                description="High-frequency service-to-service communication",
                duration_seconds=200,  # ~3 minutes
                request_rate_per_second=60,
                payload_size_kb=1,
                concurrent_connections=20,
                error_rate_percent=0.8,
                latency_variation_ms=80
            )
        ]

async def run_scenario_suite(target_url: str, scenarios: List[str] = None):
    """Run a complete suite of realistic scenarios"""
    all_scenarios = ProductionScenarios.get_scenarios()
    
    # Filter scenarios if specified
    if scenarios:
        all_scenarios = [s for s in all_scenarios if s.name in scenarios]
    
    logger.info(f"Running {len(all_scenarios)} realistic traffic scenarios")
    logger.info(f"Target service: {target_url}")
    logger.info("=" * 60)
    
    async with RealisticTrafficGenerator(target_url) as generator:
        suite_results = []
        suite_start = time.time()
        
        for i, scenario in enumerate(all_scenarios, 1):
            logger.info(f"\n[{i}/{len(all_scenarios)}] Executing scenario: {scenario.name}")
            
            try:
                result = await generator.run_traffic_pattern(scenario)
                suite_results.append(result)
                
                # Brief pause between scenarios
                logger.info("Pausing 30 seconds between scenarios...")
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Scenario '{scenario.name}' failed: {e}")
                continue
        
        suite_duration = time.time() - suite_start
        
        # Print summary
        print("\n" + "=" * 60)
        print("REALISTIC TRAFFIC SCENARIO RESULTS")
        print("=" * 60)
        
        total_requests = sum(r['requests_sent'] for r in suite_results)
        
        for result in suite_results:
            efficiency = (result['actual_rate'] / result['target_rate']) * 100
            print(f"Scenario: {result['pattern_name']}")
            print(f"  Requests: {result['requests_sent']}")
            print(f"  Duration: {result['duration']:.1f}s")
            print(f"  Rate Efficiency: {efficiency:.1f}% ({result['actual_rate']:.1f}/{result['target_rate']} req/s)")
            print()
        
        print(f"Suite Summary:")
        print(f"  Total Runtime: {suite_duration/60:.1f} minutes")
        print(f"  Total Requests: {total_requests}")
        print(f"  Average Rate: {total_requests/suite_duration:.1f} req/s")
        print(f"  Successful: {generator.metrics['successful_requests']}")
        print(f"  Failed: {generator.metrics['failed_requests']}")
        
        success_rate = (generator.metrics['successful_requests'] / generator.metrics['total_requests']) * 100
        print(f"  Success Rate: {success_rate:.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate realistic traffic patterns for testing')
    parser.add_argument('--target', default='http://speedtest-server:8080', 
                       help='Target service URL (default: speedtest-server)')
    parser.add_argument('--scenarios', nargs='*', 
                       help='Specific scenarios to run (default: all)')
    parser.add_argument('--list', action='store_true', 
                       help='List available scenarios and exit')
    
    args = parser.parse_args()
    
    if args.list:
        scenarios = ProductionScenarios.get_scenarios()
        print("Available realistic traffic scenarios:")
        print("=" * 50)
        for i, scenario in enumerate(scenarios, 1):
            print(f"{i}. {scenario.name}")
            print(f"   {scenario.description}")
            print(f"   Duration: {scenario.duration_seconds}s, Rate: {scenario.request_rate_per_second} req/s")
            print()
        return
    
    # Run the scenarios
    asyncio.run(run_scenario_suite(args.target, args.scenarios))

if __name__ == "__main__":
    main()