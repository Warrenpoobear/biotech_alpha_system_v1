from datetime import date
from src.determinism.run_id import RunConfig

def test_run_id_stable():
    cfg1 = RunConfig(as_of=date(2024,1,1), universe_version="v1", code_version="abc", weights_version="v1")
    cfg2 = RunConfig(as_of=date(2024,1,1), universe_version="v1", code_version="abc", weights_version="v1")
    assert cfg1.to_run_id() == cfg2.to_run_id()
