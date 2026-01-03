"""
QUICK TEST SCRIPT - Verify all components work.
"""
import subprocess
import sys

def test_component(name, command):
    """Test a component and return success."""
    print(f"\nTesting: {name}")
    print("-" * 40)
    
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"[OK] {name} passed")
        return True
    else:
        print(f"[FAIL] {name} failed")
        print(f"Error: {result.stderr}")
        return False

def main():
    print("WAKE ROBIN SYSTEM QUICK TEST")
    print("=" * 60)
    
    tests = [
        ("Universe Creation", [sys.executable, "define_universe_v2.py"]),
        ("Weekly Pipeline", [sys.executable, "weekly_pipeline_deterministic.py", "--date", "2024-01-15"]),
        ("Agent 4 Integration", [sys.executable, "integrate_agent4.py", "--date", "2024-01-15"]),
        ("Determinism Check", [sys.executable, "weekly_pipeline_deterministic.py", "--verify"]),
    ]
    
    all_passed = True
    for name, command in tests:
        if not test_component(name, command):
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("[OK] ALL TESTS PASSED - System is ready for production")
        return 0
    else:
        print("[FAIL] Some tests failed - Check the errors above")
        return 1

if __name__ == '__main__':
    sys.exit(main())
