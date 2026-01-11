"""
WEEKLY PIPELINE DETERMINISTIC v1.1 - Fixed for local universe files
"""
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
import sys
import hashlib
import json
import argparse
from pathlib import Path

def load_universe_from_file(date_str):
    """Load universe from local file."""
    universe_file = f"data/universe/biotech_universe_local_{date_str}.csv"
    if not os.path.exists(universe_file):
        raise FileNotFoundError(f"Universe file not found: {universe_file}")
    
    df = pd.read_csv(universe_file)
    return df

def generate_deterministic_scores(universe_df, snapshot_date):
    """
    Generate deterministic alpha scores for tickers.
    This is a MOCK detector - in production, replace with real logic.
    """
    print("   [3] Running detection (MOCK - hash-based)...")
    
    scores = []
    for _, row in universe_df.iterrows():
        ticker = row['ticker']
        
        # Create deterministic hash-based score
        hash_input = f"{ticker}_{snapshot_date.strftime('%Y-%m-%d')}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
        
        # Convert first 8 chars of hash to float between 0 and 1
        hash_int = int(hash_value[:8], 16)
        score = (hash_int % 10000) / 10000
        
        # Adjust distribution to get ~40% detection rate
        if score < 0.3:
            score = 0.3 + score * 0.5
        
        # Cap at 0.99 for realism
        score = min(0.99, score)
        
        # Create deterministic signal ID
        signal_id = f"SIG_{hash_value[:16]}"
        
        scores.append({
            'ticker': ticker,
            'score': round(score, 3),
            'signal_id': signal_id,
            'date': snapshot_date.strftime('%Y-%m-%d'),
            'detection_type': 'MOCK_HASH_BASED'
        })
    
    return pd.DataFrame(scores)

def run_weekly_pipeline(snapshot_date):
    """Main weekly pipeline function."""
    date_str = snapshot_date.strftime('%Y-%m-%d')
    
    print(f"\n{'='*70}")
    print(f"WAKE ROBIN WEEKLY PIPELINE - {date_str}")
    print(f"{'='*70}")
    
    # [1] Load deterministic universe
    print(f"\n[1] Loading deterministic universe...")
    universe_df = load_universe_from_file(date_str)
    
    print(f"   Tickers: {len(universe_df)}")
    print(f"   Market Cap Range: ${universe_df['market_cap'].min():,.0f}M - ${universe_df['market_cap'].max():,.0f}M")
    
    # [2] Initialize detector (mock)
    print(f"\n[2] Initializing detector...")
    detection_threshold = 0.7
    print(f"   Detection Threshold: {detection_threshold}")
    
    # [3] Run detection
    scores_df = generate_deterministic_scores(universe_df, snapshot_date)
    
    # [4] Generate outputs
    print(f"\n[4] Generating outputs...")
    
    # Split into detections and rejections
    detections = scores_df[scores_df['score'] >= detection_threshold].copy()
    rejections = scores_df[scores_df['score'] < detection_threshold].copy()
    
    # Sort detections by score (descending)
    detections = detections.sort_values('score', ascending=False)
    
    # Create output directory
    output_dir = f"output/weekly"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save detections
    detections_file = f"{output_dir}/detections_{date_str}.csv"
    detections.to_csv(detections_file, index=False)
    print(f"   [OK] Detections: {len(detections)} -> {detections_file}")
    
    # Save rejections
    rejections_file = f"{output_dir}/rejections_{date_str}.csv"
    rejections.to_csv(rejections_file, index=False)
    print(f"   [OK] Rejections: {len(rejections)} -> {rejections_file}")
    
    # [5] Generate summary report
    print(f"\n[5] Generating summary report...")
    
    summary = {
        'date': date_str,
        'universe_size': len(universe_df),
        'detections_count': len(detections),
        'rejections_count': len(rejections),
        'detection_rate': round(len(detections) / len(universe_df) * 100, 1),
        'detection_threshold': detection_threshold,
        'top_signals': detections.head(5)[['ticker', 'score', 'signal_id']].to_dict('records'),
        'universe_file': f"data/universe/biotech_universe_local_{date_str}.csv",
        'pipeline_version': '1.1_fixed'
    }
    
    summary_file = f"{output_dir}/summary_{date_str}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"   [OK] Summary saved: {summary_file}")
    
    # [6] Create audit hash
    print(f"\n[6] Creating audit hash...")
    
    # Combine all outputs for audit hash
    audit_data = {
        'detections': detections.to_dict('records'),
        'summary': summary
    }
    
    audit_str = json.dumps(audit_data, sort_keys=True, indent=0)
    audit_hash = hashlib.sha256(audit_str.encode()).hexdigest()
    
    audit_file = f"{output_dir}/audit_{date_str}.txt"
    with open(audit_file, 'w') as f:
        f.write(f"Audit Hash: {audit_hash}\n")
        f.write(f"Date: {date_str}\n")
        # Use snapshot_date for determinism (avoid wall-clock time)
        f.write(f"Generated: {date_str} 00:00:00\n")
    print(f"   [OK] Audit hash saved: {audit_file}")
    print(f"   Audit Hash: {audit_hash[:16]}...")
    
    # Print top 5 signals
    print(f"\n   Top 5 by score:")
    for i, row in detections.head(5).iterrows():
        print(f"      {i+1}. {row['ticker']}: {row['score']:.3f} ({row['signal_id'][:16]}...)")
    
    print(f"\n{'='*70}")
    print(f"WEEKLY PIPELINE COMPLETE")
    print(f"{'='*70}")
    
    print(f"\n[REPORT] FINAL SUMMARY:")
    print(f"   Date: {date_str}")
    print(f"   Universe: {len(universe_df)} tickers")
    print(f"   Detections: {len(detections)}")
    print(f"   Detection Rate: {summary['detection_rate']:.1f}%")
    print(f"   Top Signal: {detections.iloc[0]['ticker'] if len(detections) > 0 else 'N/A'} ({detections.iloc[0]['score'] if len(detections) > 0 else 0:.3f})")
    
    return True

def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description='Wake Robin Weekly Pipeline')
    parser.add_argument('--date', type=str, help='Snapshot date (YYYY-MM-DD)')
    parser.add_argument('--verify', action='store_true', help='Verify determinism')
    
    args = parser.parse_args()
    
    # Parse date
    if args.date:
        snapshot_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        snapshot_date = date.today()
    
    # Run pipeline
    result = run_weekly_pipeline(snapshot_date)
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())

