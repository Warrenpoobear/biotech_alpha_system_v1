import subprocess
import os
import sys
from datetime import date
import json

def run_pipeline(as_of_date: date = None, verify: bool = False, mode: str = 'demo') -> bool:
    """
    Execute the Wake Robin pipeline steps in sequence.
    
    Args:
        as_of_date: The date to run the pipeline for
        verify: If True, run verification after pipeline
        mode: 'demo' or 'production'
    
    Returns:
        bool: True if all steps succeeded, False otherwise
    """
    if as_of_date is None:
        from datetime import date
        as_of_date = date.today()
    
    date_str = as_of_date.isoformat()
    print(f"Starting pipeline for {date_str} in {mode} mode")
    
    # Define pipeline steps
    steps = [
        {
            'name': 'Create Universe',
            'command': [sys.executable, 'define_universe_v2.py', '--date', date_str]
        },
        {
            'name': 'Weekly Pipeline',
            'command': [sys.executable, 'weekly_pipeline_deterministic.py', '--date', date_str, '--mode', mode]
        },
        {
            'name': 'Agent 4 Integration',
            'command': [sys.executable, 'integrate_agent4.py', '--date', date_str]
        }
    ]
    
    # Execute each step
    for step in steps:
        print(f"\n{'-'*60}")
        print(f"Step: {step['name']}")
        print(f"Command: {' '.join(step['command'])}")
        print(f"{'-'*60}")
        
        try:
            result = subprocess.run(step['command'], capture_output=True, text=True, encoding="utf-8")
            
            if result.returncode == 0:
                print(f"[OK] {step['name']} completed successfully")
                if result.stdout.strip():
                    print(f"Output:\n{result.stdout.strip()}")
            else:
                print(f"[FAILED] {step['name']} exited with code {result.returncode}")
                print(f"Stderr:\n{result.stderr.strip()}")
                if result.stdout.strip():
                    print(f"Stdout:\n{result.stdout.strip()}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Failed to execute {step['name']}: {e}")
            return False
    
    # Run verification if requested
    if verify:
        print(f"\n{'='*60}")
        print("Starting verification process")
        print(f"{'='*60}")
        if not run_verification(as_of_date, mode):
            return False
    
    print(f"\n{'#'*60}")
    print(f"Pipeline completed successfully for {date_str}")
    print(f"{'#'*60}")
    return True

def run_verification(as_of_date: date, mode: str) -> bool:
    """Verify pipeline determinism by running twice and comparing outputs."""
    print("\n[ERROR] --verify is not implemented in this v1.1 rewrite.")
    print("        Use the existing determinism checks in weekly_pipeline_deterministic.py --verify")
    print("        or re-add your prior output hash comparison harness.")
    return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Wake Robin pipeline")
    parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format')
    parser.add_argument('--verify', action='store_true', help='Run verification after pipeline')
    parser.add_argument('--mode', type=str, default='demo', choices=['demo', 'production'])
    
    args = parser.parse_args()
    
    run_date = date.fromisoformat(args.date) if args.date else None
    success = run_pipeline(as_of_date=run_date, verify=args.verify, mode=args.mode)
    
    sys.exit(0 if success else 1)