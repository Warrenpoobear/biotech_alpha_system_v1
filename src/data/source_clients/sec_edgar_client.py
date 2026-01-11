"""SEC EDGAR client (networking allowed ONLY here).

Supports:
- 13F filings (institutional ownership changes)
- Form 4 (insider transactions)
- 8-K filings (material events)

Data is loaded from local files or fetched from SEC EDGAR API.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd


class SECEdgarAPIError(RuntimeError):
    """Raised when SEC EDGAR API returns an error."""
    pass


class SECEdgarClient:
    """SEC EDGAR API client.

    Production implementation uses SEC EDGAR REST API.
    Rate limited to 10 requests/second per SEC guidelines.
    """

    BASE_URL = "https://data.sec.gov"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions"

    def __init__(self, *, timeout_s: int = 30, max_retries: int = 3, rps: float = 10.0):
        self.timeout_s = timeout_s
        self.min_delay_s = 1.0 / max(rps, 0.1)
        self._last_req = 0.0

        sess = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        sess.mount("https://", HTTPAdapter(max_retries=retry))
        self.session = sess

        # SEC requires a user agent with contact info
        ua = os.getenv("SEC_USER_AGENT", "BiotechAlphaSystem/1.0 (fixtures_builder@example.com)")
        self.headers = {"User-Agent": ua, "Accept": "application/json"}

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        now = time.time()
        delta = now - self._last_req
        if delta < self.min_delay_s:
            time.sleep(self.min_delay_s - delta)
        self._last_req = time.time()

    def fetch_filings(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch SEC filings for universe tickers.

        Returns DataFrame with columns:
        - ticker: Stock ticker
        - filing_type: 13F-HR, 4, 8-K, etc.
        - filing_date: Date of filing
        - filer_name: Name of filer (institution or insider)
        - transaction_type: BUY, SELL, GRANT, etc.
        - shares: Number of shares
        - value_usd: Dollar value of transaction
        - description: Filing description
        """
        rows: List[Dict[str, Any]] = []

        for _, r in universe_df.iterrows():
            ticker = str(r.get("ticker", "")).upper().strip()
            cik = str(r.get("cik", "")).strip() if "cik" in r else None

            if not ticker:
                continue

            # If we have a CIK, fetch filings
            if cik:
                try:
                    filings = self._fetch_company_filings(cik, as_of)
                    for f in filings:
                        f["ticker"] = ticker
                        rows.append(f)
                except SECEdgarAPIError:
                    # Log error but continue with other tickers
                    pass

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["ticker", "filing_date", "filing_type"], kind="mergesort").reset_index(drop=True)
        return df

    def _fetch_company_filings(self, cik: str, as_of: date, lookback_days: int = 90) -> List[Dict[str, Any]]:
        """Fetch recent filings for a company by CIK."""
        self._rate_limit()

        # Pad CIK to 10 digits
        cik_padded = cik.zfill(10)
        url = f"{self.SUBMISSIONS_URL}/CIK{cik_padded}.json"

        resp = self.session.get(url, headers=self.headers, timeout=self.timeout_s)
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            raise SECEdgarAPIError(f"SEC EDGAR HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        filings = data.get("filings", {}).get("recent", {})

        # Extract relevant filings
        results = []
        cutoff = as_of - timedelta(days=lookback_days)

        form_types = filings.get("form", [])
        filing_dates = filings.get("filingDate", [])
        primary_docs = filings.get("primaryDocument", [])
        accession_nums = filings.get("accessionNumber", [])

        for i, form_type in enumerate(form_types):
            if i >= len(filing_dates):
                break

            filing_date_str = filing_dates[i]
            try:
                filing_date = date.fromisoformat(filing_date_str)
            except (ValueError, TypeError):
                continue

            # Filter by date range
            if filing_date < cutoff or filing_date > as_of:
                continue

            # Only include relevant form types
            if form_type not in ("13F-HR", "13F-HR/A", "4", "4/A", "8-K", "8-K/A"):
                continue

            results.append({
                "filing_type": form_type.replace("/A", ""),  # Normalize amendments
                "filing_date": filing_date_str,
                "filer_name": data.get("name", ""),
                "transaction_type": self._infer_transaction_type(form_type),
                "shares": None,
                "value_usd": None,
                "description": f"{form_type} filing",
                "accession_number": accession_nums[i] if i < len(accession_nums) else None,
            })

        return results

    @staticmethod
    def _infer_transaction_type(form_type: str) -> str:
        """Infer transaction type from form type."""
        if "13F" in form_type:
            return "INSTITUTIONAL_HOLDING"
        if form_type.startswith("4"):
            return "INSIDER_TRANSACTION"
        if "8-K" in form_type:
            return "MATERIAL_EVENT"
        return "OTHER"


class SECEdgarFileClient(SECEdgarClient):
    """SEC EDGAR client that loads from local CSV files."""

    def __init__(self, data_dir: Path = Path("data/sec")):
        self.data_dir = data_dir

    def fetch_filings(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Load filings from local CSV files."""
        tickers = set(str(t).upper().strip() for t in universe_df["ticker"].tolist())
        filings = self._load_from_files(as_of, tickers)

        if filings.empty:
            return pd.DataFrame(columns=[
                "ticker", "filing_type", "filing_date", "filer_name",
                "transaction_type", "shares", "value_usd", "description"
            ])

        return filings

    def _load_from_files(self, as_of: date, tickers: set) -> pd.DataFrame:
        """Load filings from local CSV files."""
        all_rows: List[Dict[str, Any]] = []

        # Look for quarterly or date-specific files
        for pattern in [
            f"filings_{as_of.isoformat()}.csv",
            f"filings_{as_of.year}Q{(as_of.month - 1) // 3 + 1}.csv",
            "filings_latest.csv",
        ]:
            file_path = self.data_dir / pattern
            if file_path.exists():
                df = pd.read_csv(file_path)
                df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
                df = df[df["ticker"].isin(tickers)]

                for _, row in df.iterrows():
                    all_rows.append({
                        "ticker": row.get("ticker", ""),
                        "filing_type": row.get("filing_type", ""),
                        "filing_date": row.get("filing_date", ""),
                        "filer_name": row.get("filer_name", ""),
                        "transaction_type": row.get("transaction_type", ""),
                        "shares": self._safe_float(row.get("shares")),
                        "value_usd": self._safe_float(row.get("value_usd")),
                        "description": row.get("description", ""),
                    })
                break  # Use first matching file

        return pd.DataFrame(all_rows)

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert value to float."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


@dataclass(frozen=True)
class DemoSECEdgarClient(SECEdgarClient):
    """Offline demo client with sample SEC filing data."""

    # Sample filings for major biotech tickers
    SAMPLE_FILINGS: Dict[str, List[Dict[str, Any]]] = {
        "MRNA": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "Vanguard Group",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 45_000_000, "value_usd": 4_500_000_000,
             "description": "Q4 2023 institutional holdings"},
            {"filing_type": "4", "filing_date": "2024-01-15", "filer_name": "Stephane Bancel (CEO)",
             "transaction_type": "SELL", "shares": 50_000, "value_usd": 5_000_000,
             "description": "10b5-1 planned sale"},
            {"filing_type": "8-K", "filing_date": "2024-01-22", "filer_name": "Moderna Inc",
             "transaction_type": "MATERIAL_EVENT", "shares": None, "value_usd": None,
             "description": "Quarterly earnings announcement"},
        ],
        "GILD": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "BlackRock Inc",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 85_000_000, "value_usd": 6_800_000_000,
             "description": "Q4 2023 institutional holdings"},
            {"filing_type": "4", "filing_date": "2024-01-10", "filer_name": "Daniel O'Day (CEO)",
             "transaction_type": "BUY", "shares": 10_000, "value_usd": 800_000,
             "description": "Open market purchase"},
        ],
        "VRTX": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "State Street Corp",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 12_000_000, "value_usd": 4_800_000_000,
             "description": "Q4 2023 institutional holdings"},
            {"filing_type": "8-K", "filing_date": "2024-02-05", "filer_name": "Vertex Pharmaceuticals",
             "transaction_type": "MATERIAL_EVENT", "shares": None, "value_usd": None,
             "description": "FDA approval announcement"},
        ],
        "REGN": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "Fidelity Management",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 8_500_000, "value_usd": 7_500_000_000,
             "description": "Q4 2023 institutional holdings"},
            {"filing_type": "4", "filing_date": "2024-01-20", "filer_name": "Leonard Schleifer (CEO)",
             "transaction_type": "GRANT", "shares": 25_000, "value_usd": 22_000_000,
             "description": "Stock option exercise"},
        ],
        "BIIB": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "Capital Research",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 15_000_000, "value_usd": 3_500_000_000,
             "description": "Q4 2023 institutional holdings"},
            {"filing_type": "8-K", "filing_date": "2024-01-30", "filer_name": "Biogen Inc",
             "transaction_type": "MATERIAL_EVENT", "shares": None, "value_usd": None,
             "description": "Leqembi sales update"},
        ],
        "ALNY": [
            {"filing_type": "4", "filing_date": "2024-01-25", "filer_name": "Yvonne Greenstreet (CEO)",
             "transaction_type": "SELL", "shares": 15_000, "value_usd": 2_700_000,
             "description": "10b5-1 planned sale"},
        ],
        "BMRN": [
            {"filing_type": "13F-HR", "filing_date": "2024-02-14", "filer_name": "T. Rowe Price",
             "transaction_type": "INSTITUTIONAL_HOLDING", "shares": 18_000_000, "value_usd": 1_500_000_000,
             "description": "Q4 2023 institutional holdings"},
        ],
        "INCY": [
            {"filing_type": "4", "filing_date": "2024-01-18", "filer_name": "Herve Hoppenot (CEO)",
             "transaction_type": "SELL", "shares": 30_000, "value_usd": 1_800_000,
             "description": "10b5-1 planned sale"},
            {"filing_type": "8-K", "filing_date": "2024-02-01", "filer_name": "Incyte Corp",
             "transaction_type": "MATERIAL_EVENT", "shares": None, "value_usd": None,
             "description": "Pipeline update presentation"},
        ],
    }

    def fetch_filings(self, as_of: date, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Return sample SEC filing data for demo/testing."""
        rows = []
        for _, r in universe_df.iterrows():
            ticker = str(r["ticker"]).upper().strip()
            if ticker in self.SAMPLE_FILINGS:
                for filing in self.SAMPLE_FILINGS[ticker]:
                    rows.append({"ticker": ticker, **filing})

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=[
                "ticker", "filing_type", "filing_date", "filer_name",
                "transaction_type", "shares", "value_usd", "description"
            ])

        df = df.sort_values(["ticker", "filing_date", "filing_type"], kind="mergesort").reset_index(drop=True)
        return df
