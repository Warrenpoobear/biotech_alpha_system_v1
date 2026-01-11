"""
AGENT 4 INTEGRATION - Maps Wake Robin signals to Agent 4 composite ranker format.
"""
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, ValidationError


class DetectionRecord(BaseModel):
    """Schema for validating detection records from Wake Robin."""
    ticker: str = Field(..., min_length=1, max_length=10)
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    alpha_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    signal_id: Optional[str] = None
    date: Optional[str] = None
    detection_type: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        return v.upper().strip()

    def get_score_value(self) -> float:
        """Get the score value, preferring 'score' over 'alpha_score'."""
        if self.score is not None:
            return self.score
        if self.alpha_score is not None:
            return self.alpha_score
        raise ValueError("Detection must have 'score' or 'alpha_score'")

    model_config = {"extra": "ignore"}


def validate_detections_df(df: pd.DataFrame) -> List[DetectionRecord]:
    """Validate DataFrame against DetectionRecord schema."""
    if df.empty:
        return []

    # Check for required column
    if "ticker" not in df.columns:
        raise ValueError("Detection DataFrame must have 'ticker' column")

    if "score" not in df.columns and "alpha_score" not in df.columns:
        raise ValueError("Detection DataFrame must have 'score' or 'alpha_score' column")

    validated_records = []
    errors = []

    for idx, row in df.iterrows():
        try:
            record = DetectionRecord(**row.to_dict())
            validated_records.append(record)
        except ValidationError as e:
            errors.append(f"Row {idx}: {e}")

    if errors:
        raise ValueError(f"Validation failed for {len(errors)} rows:\n" + "\n".join(errors[:5]))

    return validated_records


def map_to_agent4_format(detections_df, as_of_date):
    """Map Wake Robin detections to Agent 4 format."""
    agent4_signals = []
    
    for _, row in detections_df.iterrows():
        # Check if we have 'score' or 'alpha_score' column
        if 'score' in row:
            score_value = row['score']
        elif 'alpha_score' in row:
            score_value = row['alpha_score']
        else:
            raise KeyError("Detection dataframe must have 'score' or 'alpha_score' column")
        
        # Create deterministic signal ID
        signal_input = f"{row['ticker']}_{as_of_date}_{score_value:.4f}"
        signal_hash = hashlib.sha256(signal_input.encode()).hexdigest()[:12]
        signal_id = f"A4_{signal_hash}"
        
        agent4_signals.append({
            'security_id': row['ticker'],
            'alpha_score': float(score_value),
            'confidence': 1.0,  # Placeholder - in production would be based on signal strength
            'signal_id': signal_id,
            'as_of_date': as_of_date,
            'signal_type': 'biotech_alpha',
            'components': {
                'wake_robin_score': float(score_value),
                'signal_source': 'wake_robin_v1',
                'detection_date': as_of_date
            }
        })
    
    return pd.DataFrame(agent4_signals)

def integrate_with_agent4(as_of_date):
    """Main integration function."""
    date_str = as_of_date.strftime('%Y-%m-%d')
    
    print(f"\n{'='*70}")
    print(f"AGENT 4 INTEGRATION - {date_str}")
    print(f"{'='*70}")
    
    # [1] Load Wake Robin detections
    print(f"\n[1] Loading Wake Robin detections...")
    detections_file = f"output/weekly/detections_{date_str}.csv"

    if not os.path.exists(detections_file):
        raise FileNotFoundError(f"Detections file not found: {detections_file}")

    detections_df = pd.read_csv(detections_file)
    print(f"   Found {len(detections_df)} DETECT signals")

    # [1.5] Validate detection schema
    print(f"\n[1.5] Validating detection schema...")
    try:
        validated_records = validate_detections_df(detections_df)
        print(f"   Validated {len(validated_records)} records")
    except ValueError as e:
        print(f"   [ERROR] Schema validation failed: {e}")
        raise

    # [2] Map to Agent 4 format
    print(f"\n[2] Mapping to Agent 4 format...")
    agent4_signals = map_to_agent4_format(detections_df, date_str)
    print(f"   Mapped {len(agent4_signals)} signals")
    
    # [3] Save Agent 4 output
    print(f"\n[3] Saving Agent 4 output...")
    
    # Create output directory
    output_dir = f"output/agent4"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save CSV
    csv_file = f"{output_dir}/agent4_signals_{date_str}.csv"
    agent4_signals.to_csv(csv_file, index=False)
    
    # Save JSON
    json_file = f"{output_dir}/agent4_signals_{date_str}.json"
    with open(json_file, 'w') as f:
        json.dump(agent4_signals.to_dict('records'), f, indent=2)
    
    # Create hash file
    hash_str = hashlib.sha256(agent4_signals.to_csv(index=False).encode()).hexdigest()
    hash_file = f"{output_dir}/agent4_hash_{date_str}.txt"
    with open(hash_file, 'w') as f:
        f.write(f"Agent 4 Signals Hash: {hash_str}\n")
        f.write(f"Date: {date_str}\n")
        f.write(f"Signal count: {len(agent4_signals)}\n")
    
    print(f"[OK] Agent 4 signals saved:")
    print(f"   CSV: {csv_file}")
    print(f"   JSON: {json_file}")
    print(f"   Hash: {hash_file}")
    print(f"   Signal count: {len(agent4_signals)}")
    print(f"   Hash value: {hash_str[:16]}...")
    
    # [4] Print sample signals
    print(f"\n[4] Sample signals (top 3):")
    for i, row in agent4_signals.head(3).iterrows():
        print(f"   {i+1}. {row['security_id']}:")
        print(f"      Alpha Score: {row['alpha_score']:.3f}")
        print(f"      Confidence: {row['confidence']:.3f}")
        print(f"      Signal ID: {row['signal_id']}")
    
    print(f"\n{'='*70}")
    print(f"INTEGRATION COMPLETE")
    print(f"{'='*70}")
    
    return True

def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description='Integrate Wake Robin signals with Agent 4')
    parser.add_argument('--date', type=str, help='Snapshot date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Parse date
    if args.date:
        as_of_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        as_of_date = date.today()
    
    # Run integration
    result = integrate_with_agent4(as_of_date)
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())
