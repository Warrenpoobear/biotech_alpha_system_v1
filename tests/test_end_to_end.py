import shutil
from pathlib import Path
from subprocess import check_call
import sys

def test_pipeline_runs(tmp_path):
    # Copy repo fixtures into tmp and run
    repo = Path(__file__).resolve().parents[1]
    work = tmp_path / "repo"
    shutil.copytree(repo, work)

    # Run pipeline twice and compare screen_results.json
    cmd = [sys.executable, "run_pipeline.py", "--as-of", "2024-01-01", "--fixtures", "fixtures", "--artifacts", "artifacts"]
    check_call(cmd, cwd=work)
    first = next((work/"artifacts"/"runs").iterdir())
    screen1 = (first/"screen_results.json").read_bytes()

    # Clean artifacts and re-run
    shutil.rmtree(work/"artifacts")
    (work/"artifacts").mkdir()
    check_call(cmd, cwd=work)
    second = next((work/"artifacts"/"runs").iterdir())
    screen2 = (second/"screen_results.json").read_bytes()

    assert screen1 == screen2
