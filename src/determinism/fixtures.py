"""Immutable fixture system (PIT inputs).

- Supports Parquet if available; otherwise CSV/JSON fallback.
- Writes `.sha256` alongside fixture content.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import hashlib
import json
from typing import List, Optional, Tuple

import pandas as pd

class FixtureError(Exception): ...
class FixtureMissingError(FixtureError): ...
class FixtureValidationError(FixtureError): ...

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

@dataclass(frozen=True)
class FixtureRef:
    as_of: date
    source: str
    path: Path
    sha256: str

class FixtureManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def _dir(self, as_of: date) -> Path:
        return self.base_path / f"asof={as_of.isoformat()}"

    def get_paths(self, as_of: date, source: str) -> Tuple[Path, Path]:
        d = self._dir(as_of)
        # Prefer parquet
        pq = d / f"{source}.parquet"
        csv = d / f"{source}.csv"
        js = d / f"{source}.json"
        sha = None
        if pq.exists():
            sha = pq.with_suffix(pq.suffix + ".sha256")
            return pq, sha
        if csv.exists():
            sha = csv.with_suffix(csv.suffix + ".sha256")
            return csv, sha
        if js.exists():
            sha = js.with_suffix(js.suffix + ".sha256")
            return js, sha
        # default (parquet) location
        sha = pq.with_suffix(pq.suffix + ".sha256")
        return pq, sha

    def load_df(self, as_of: date, source: str, required_columns: Optional[List[str]] = None) -> pd.DataFrame:
        path, _ = self.get_paths(as_of, source)
        if not path.exists():
            raise FixtureMissingError(f"Fixture not found: {path}")

        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        elif path.suffix == ".csv":
            df = pd.read_csv(path)
        elif path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            df = pd.DataFrame(obj)
        else:
            raise FixtureValidationError(f"Unsupported fixture format: {path.suffix}")

        if required_columns:
            missing = set(required_columns) - set(df.columns)
            if missing:
                raise FixtureValidationError(f"Missing required columns in {source}: {sorted(missing)}")
        return df

    def create_df_fixture(self, df: pd.DataFrame, as_of: date, source: str, fmt: str = "parquet") -> FixtureRef:
        d = self._dir(as_of)
        d.mkdir(parents=True, exist_ok=True)

        if fmt == "parquet":
            path = d / f"{source}.parquet"
            df.to_parquet(path, index=False)
        elif fmt == "csv":
            path = d / f"{source}.csv"
            df.to_csv(path, index=False)
        else:
            raise FixtureValidationError("fmt must be 'parquet' or 'csv'")

        sha = _sha256_file(path)
        sha_path = path.with_suffix(path.suffix + ".sha256")
        sha_path.write_text(sha, encoding="utf-8")
        return FixtureRef(as_of=as_of, source=source, path=path, sha256=sha)
