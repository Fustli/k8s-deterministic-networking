#!/usr/bin/env python3
"""
Comprehensive Test Runner for K8s Deterministic Networking

Runs all test suites with proper reporting and logging.
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path
import time
from datetime import datetime

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

class TestRunner:
    """Manages test execution and reporting"""
    
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.test_dir = ROOT / "tests"
        self.results = {}
    
    def run_command(self, cmd, description=""):
        """Run command and capture output"""
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Running: {description}")
            print(f"Command: {cmd}")
            print('='*60)
        
        start_time = time.time()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        duration = time.time() - start_time
        
        if self.verbose:
            print(f"Exit code: {result.returncode}")
            print(f"Duration: {duration:.2f}s")
            if result.stdout:
                print(f"STDOUT:\n{result.stdout}")
            if result.stderr and result.returncode != 0:
                print(f"STDERR:\n{result.stderr}")
        
        return result.returncode == 0, result.stdout, result.stderr, duration
    
    def check_prerequisites(self):
        """Check that all prerequisites are met"""
        print("Checking Prerequisites...")
        
        # Check Python dependencies
        required_modules = ['pytest', 'kubernetes']
        missing_modules = []
        
        for module in required_modules:
            try:
                __import__(module)
                if self.verbose:
                    print(f"[OK] {module} available")
            except ImportError:
                missing_modules.append(module)
                print(f"[ERROR] {module} missing")
        
        if missing_modules:
            print(f"\n[WARNING] Missing dependencies: {missing_modules}")
            print("Install with: pip install pytest kubernetes prometheus-api-client")
            return False
        
        # Check kubectl access
        success, _, _, _ = self.run_command("kubectl version --client", "Checking kubectl")
        if not success:
            print("[ERROR] kubectl not available")
            return False
        print("[OK] kubectl available")
        
        # Check cluster access
        success, output, _, _ = self.run_command("kubectl get nodes", "Checking cluster access")
        if not success:
            print("[ERROR] Cannot access Kubernetes cluster")
            return False
        print("[OK] Cluster access working")
        
        return True
    
    def run_unit_tests(self):
        """Run unit tests (no cluster dependencies)"""
        print("\n🧪 Running Unit Tests...")
        
        cmd = f"cd {ROOT} && python3 -m pytest tests/unit/ -v --tb=short"
        success, stdout, stderr, duration = self.run_command(cmd, "Unit Tests")
        
        self.results['unit'] = {
            'success': success,
            'duration': duration,
            'output': stdout
        }
        
        return success
    
    def run_integration_tests(self):
        """Run integration tests (require cluster)"""
        print("\nRunning Integration Tests...")
        
        cmd = f"cd {ROOT} && python3 -m pytest tests/integration/ -v --tb=short -m 'not slow'"
        success, stdout, stderr, duration = self.run_command(cmd, "Integration Tests (Fast)")
        
        self.results['integration'] = {
            'success': success,
            'duration': duration,
            'output': stdout
        }
        
        return success
    
    def run_e2e_tests(self, include_slow=False):
        """Run end-to-end tests"""
        print("\nRunning End-to-End Tests...")
        
        marker = "" if include_slow else "-m 'not slow'"
        cmd = f"cd {ROOT} && python3 -m pytest tests/e2e/ -v --tb=short {marker}"
        success, stdout, stderr, duration = self.run_command(cmd, "E2E Tests")
        
        self.results['e2e'] = {
            'success': success,
            'duration': duration,
            'output': stdout
        }
        
        return success
    
    def run_live_system_test(self):
        """Run quick live system verification"""
        print("\nRunning Live System Test...")
        
        # Use our existing test scripts
        scripts = [
            "test_bandwidth_control.py",
            "comprehensive_test.py"
        ]
        
        for script in scripts:
            script_path = ROOT / script
            if script_path.exists():
                cmd = f"cd {ROOT} && python3 {script}"
                success, stdout, stderr, duration = self.run_command(cmd, f"Live Test: {script}")
                
                if not success:
                    print(f"[ERROR] Live test failed: {script}")
                    return False
        
        print("[OK] Live system tests passed")
        return True
    
    def generate_report(self):
        """Generate test report"""
        print("\n" + "="*80)
        print("TEST EXECUTION REPORT")
        print("="*80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        total_duration = sum(r.get('duration', 0) for r in self.results.values())
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r.get('success', False))
        
        print(f"\nOverall Results:")
        print(f"  Total Test Suites: {total_tests}")
        print(f"  Passed: {passed_tests}")
        print(f"  Failed: {total_tests - passed_tests}")
        print(f"  Total Duration: {total_duration:.2f}s")
        
        print(f"\nDetailed Results:")
        for suite_name, result in self.results.items():
            status = "[PASS]" if result.get('success', False) else "[FAIL]"
            duration = result.get('duration', 0)
            print(f"  {status} {suite_name.capitalize():15} ({duration:5.2f}s)")
            
            # Extract test counts from output
            output = result.get('output', '')
            if 'passed' in output or 'failed' in output:
                # Try to extract pytest summary
                lines = output.split('\n')
                summary_lines = [l for l in lines if ' passed' in l or ' failed' in l or ' error' in l]
                if summary_lines:
                    print(f"      {summary_lines[-1].strip()}")
        
        # Overall assessment
        print(f"\n{'='*80}")
        if passed_tests == total_tests:
            print("[SUCCESS] ALL TESTS PASSED! System is ready for production.")
        elif passed_tests >= total_tests * 0.8:
            print("[WARNING] Most tests passed. Review failures before production.")
        else:
            print("[ERROR] Significant test failures. System needs attention.")
        
        print("="*80)
        
        return passed_tests == total_tests


def main():
    """Main test runner entry point"""
    parser = argparse.ArgumentParser(description="K8s Deterministic Networking Test Suite")
    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration-only", action="store_true", help="Run only integration tests")
    parser.add_argument("--e2e-only", action="store_true", help="Run only E2E tests")
    parser.add_argument("--include-slow", action="store_true", help="Include slow tests")
    parser.add_argument("--skip-prereqs", action="store_true", help="Skip prerequisite checks")
    parser.add_argument("--live-test", action="store_true", help="Run live system tests")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    runner = TestRunner(verbose=not args.quiet)
    
    print("K8s Deterministic Networking - Test Suite")
    print("="*80)
    
    # Prerequisites
    if not args.skip_prereqs:
        if not runner.check_prerequisites():
            print("[ERROR] Prerequisites not met. Exiting.")
            return 1
    
    success_count = 0
    total_count = 0
    
    # Run selected tests
    if args.unit_only:
        total_count = 1
        if runner.run_unit_tests():
            success_count += 1
    elif args.integration_only:
        total_count = 1  
        if runner.run_integration_tests():
            success_count += 1
    elif args.e2e_only:
        total_count = 1
        if runner.run_e2e_tests(args.include_slow):
            success_count += 1
    elif args.live_test:
        total_count = 1
        if runner.run_live_system_test():
            success_count += 1
    else:
        # Run all tests
        tests = [
            runner.run_unit_tests,
            runner.run_integration_tests,
            lambda: runner.run_e2e_tests(args.include_slow)
        ]
        
        if args.live_test:
            tests.append(runner.run_live_system_test)
        
        total_count = len(tests)
        for test_func in tests:
            if test_func():
                success_count += 1
    
    # Generate report
    all_passed = runner.generate_report()
    
    # Return appropriate exit code
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())