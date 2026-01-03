#!/usr/bin/env python3
"""
WAKE ROBIN PILOT ORACLE v1.1
Validates core detector logic and determinism.
Now with proper config file reading and detailed signal output.
"""
import sys
import os
import yaml
import hashlib
import json
from datetime import date, datetime
from typing import Dict, List, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Mock data for pilot testing
PILOT_UNIVERSE = {
    'AMGN': {
        'catalyst_verified': True,
        'data_sufficient': True,
        'timing_suitable': True,
        'probability': 0.75,
        'capital_risk': 0.3,
        'catalyst_date': '2024-03-15',
        'tier': 'tier1'
    },
    'VRTX': {
        'catalyst_verified': True,
        'data_sufficient': True,
        'timing_suitable': True,
        'probability': 0.80,
        'capital_risk': 0.25,
        'catalyst_date': '2024-04-01',
        'tier': 'tier1'
    },
    'AKRO': {
        'catalyst_verified': False,  # CATALYST_UNVERIFIED
        'data_sufficient': True,
        'timing_suitable': True,
        'probability': 0.65,
        'capital_risk': 0.4,
        'catalyst_date': None,
        'tier': 'tier2'
    },
    'MISSING': {
        'catalyst_verified': True,
        'data_sufficient': False,  # DATA_INSUFFICIENT
        'timing_suitable': True,
        'probability': 0.70,
        'capital_risk': 0.35,
        'catalyst_date': '2024-05-01',
        'tier': 'tier1'
    },
    'EARLY': {
        'catalyst_verified': True,
        'data_sufficient': True,
        'timing_suitable': False,  # TIMING_UNSUITABLE (too early)
        'probability': 0.72,
        'capital_risk': 0.32,
        'catalyst_date': '2024-06-30',
        'tier': 'tier1'
    },
    'LOWPOS': {
        'catalyst_verified': True,
        'data_sufficient': True,
        'timing_suitable': True,
        'probability': 0.35,  # PROBABILITY_TOO_LOW
        'capital_risk': 0.28,
        'catalyst_date': '2024-03-01',
        'tier': 'tier2'
    },
    'RISKY': {
        'catalyst_verified': True,
        'data_sufficient': True,
        'timing_suitable': True,
        'probability': 0.68,
        'capital_risk': 0.85,  # CAPITAL_RISK_HIGH
        'catalyst_date': '2024-02-28',
        'tier': 'tier2'
    }
}

EXPECTED_DECISIONS = {
    'AMGN': 'DETECT',
    'VRTX': 'DETECT',
    'AKRO': 'REJECT',
    'MISSING': 'REJECT',
    'EARLY': 'REJECT',
    'LOWPOS': 'REJECT',
    'RISKY': 'REJECT'
}

REJECTION_REASONS = {
    'AKRO': 'CATALYST_UNVERIFIED',
    'MISSING': 'DATA_INSUFFICIENT',
    'EARLY': 'TIMING_UNSUITABLE',
    'LOWPOS': 'PROBABILITY_TOO_LOW',
    'RISKY': 'CAPITAL_RISK_HIGH'
}


class PilotDetector:
    """Pilot detector that actually reads config files."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.weights = self._load_config("tier_weights_v1.yaml")
        self.thresholds = self._load_config("thresholds_v1.yaml")
        
        if not self.weights:
            print("⚠️  WARNING: Using hardcoded fallback weights (config not found)")
            self.weights = {
                'tier1_weights': {
                    'catalyst_setup': 0.15,
                    'probability_of_success': 0.15,
                    'payoff_asymmetry': 0.20,
                    'capital_risk': 0.10,
                    'data_coverage': 0.05,
                    'positioning_sentiment': 0.35
                },
                'tier2_weights': {
                    'catalyst_setup': 0.25,
                    'probability_of_success': 0.25,
                    'payoff_asymmetry': 0.20,
                    'capital_risk': 0.15,
                    'data_coverage': 0.05,
                    'positioning_sentiment': 0.10
                }
            }
        
        self.detection_threshold = self.thresholds.get('detection_threshold', 0.70) if self.thresholds else 0.70
        
    def _load_config(self, filename: str) -> Dict[str, Any]:
        """Load YAML configuration file."""
        path = os.path.join(self.config_dir, filename)
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}
        except yaml.YAMLError as e:
            print(f"⚠️  Error parsing {filename}: {e}")
            return {}
    
    def _calculate_score(self, ticker_data: Dict[str, Any]) -> float:
        """Calculate detection score based on config weights."""
        tier = ticker_data.get('tier', 'tier1')
        weights = self.weights.get(f'{tier}_weights', {})
        
        if not weights:
            # Fallback to tier1 weights if tier-specific not found
            weights = self.weights.get('tier1_weights', {})
        
        # Simple scoring logic for pilot
        score = 0.0
        
        # Catalyst verification
        if ticker_data.get('catalyst_verified'):
            score += weights.get('catalyst_setup', 0.15) * 1.0
        
        # Data sufficiency
        if ticker_data.get('data_sufficient'):
            score += weights.get('data_coverage', 0.05) * 1.0
        
        # Timing suitability
        if ticker_data.get('timing_suitable'):
            score += weights.get('positioning_sentiment', 0.35) * 0.8  # Reduced for timing
        
        # Probability contribution
        probability = ticker_data.get('probability', 0.5)
        score += weights.get('probability_of_success', 0.15) * probability
        
        # Risk adjustment (inverse)
        risk = ticker_data.get('capital_risk', 0.5)
        score += weights.get('capital_risk', 0.10) * (1.0 - risk)
        
        # Payoff asymmetry (mocked)
        score += weights.get('payoff_asymmetry', 0.20) * 0.7
        
        # Normalize to 0-1
        return min(1.0, max(0.0, score))
    
    def _check_rejection(self, ticker_data: Dict[str, Any]) -> tuple:
        """Check if ticker should be rejected and return reason."""
        
        # Check kill switches from config
        kill_switches = self.thresholds.get('kill_switches', {}) if self.thresholds else {}
        
        # 1. Catalyst verification
        if not ticker_data.get('catalyst_verified', True):
            return False, 'CATALYST_UNVERIFIED'
        
        # 2. Data sufficiency
        if not ticker_data.get('data_sufficient', True):
            return False, 'DATA_INSUFFICIENT'
        
        # 3. Timing suitability
        if not ticker_data.get('timing_suitable', True):
            return False, 'TIMING_UNSUITABLE'
        
        # 4. Probability threshold
        min_pos = kill_switches.get('pos_min', 0.25)
        if ticker_data.get('probability', 0) < min_pos:
            return False, 'PROBABILITY_TOO_LOW'
        
        # 5. Capital risk
        max_risk = 0.8  # Default if not in config
        if ticker_data.get('capital_risk', 0) > max_risk:
            return False, 'CAPITAL_RISK_HIGH'
        
        return True, None
    
    def _generate_signal_payload(self, ticker: str, ticker_data: Dict[str, Any], 
                               score: float, decision: str, reason: str = None) -> Dict[str, Any]:
        """Generate detailed signal payload."""
        # Create deterministic hash
        hash_input = f"{ticker}_{score}_{decision}_{reason or ''}"
        calc_hash = hashlib.md5(hash_input.encode()).hexdigest()
        
        # Determine tier weights used
        tier = ticker_data.get('tier', 'tier1')
        weights = self.weights.get(f'{tier}_weights', {})
        
        # Create component scores
        components = {
            'catalyst_quality': 1.0 if ticker_data.get('catalyst_verified') else 0.0,
            'data_coverage': 1.0 if ticker_data.get('data_sufficient') else 0.0,
            'timing_score': 1.0 if ticker_data.get('timing_suitable') else 0.0,
            'probability_score': ticker_data.get('probability', 0.5),
            'risk_score': 1.0 - ticker_data.get('capital_risk', 0.5),
            'payoff_score': 0.7  # Mocked
        }
        
        # Apply weights to components
        weighted_components = {}
        for comp, value in components.items():
            weight_key = {
                'catalyst_quality': 'catalyst_setup',
                'data_coverage': 'data_coverage',
                'timing_score': 'positioning_sentiment',
                'probability_score': 'probability_of_success',
                'risk_score': 'capital_risk',
                'payoff_score': 'payoff_asymmetry'
            }.get(comp, 'catalyst_setup')
            
            weight = weights.get(weight_key, 0.15)
            weighted_components[f"{comp}_weighted"] = value * weight
        
        # Signal payload
        payload = {
            'signal_id': f"SIG_{calc_hash[:8]}",
            'ticker': ticker,
            'timestamp': datetime.now().isoformat(),
            'decision': decision,
            'total_score': round(score, 4),
            'threshold': self.detection_threshold,
            'calc_hash': calc_hash[:16],
            'components': {k: round(v, 4) for k, v in components.items()},
            'weighted_components': weighted_components,
            'tier': tier,
            'weights_used': weights,
            'metadata': {
                'catalyst_date': ticker_data.get('catalyst_date'),
                'probability': ticker_data.get('probability'),
                'capital_risk': ticker_data.get('capital_risk'),
                'data_source': 'pilot_mock_v1'
            }
        }
        
        if reason:
            payload['rejection_reason'] = reason
            payload['rejection_details'] = {
                'rule_triggered': reason,
                'config_threshold': self.thresholds.get('kill_switches', {}).get('pos_min', 0.25) 
                                   if reason == 'PROBABILITY_TOO_LOW' else 'N/A'
            }
        
        return payload
    
    def process_ticker(self, ticker: str, as_of_date: date, 
                      ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single ticker and return decision with payload."""
        # Check rejection criteria first
        should_process, rejection_reason = self._check_rejection(ticker_data)
        
        if not should_process:
            score = 0.0
            decision = 'REJECT'
            payload = self._generate_signal_payload(
                ticker, ticker_data, score, decision, rejection_reason
            )
            return payload
        
        # Calculate score
        score = self._calculate_score(ticker_data)
        
        # Make decision
        decision = 'DETECT' if score >= self.detection_threshold else 'REJECT'
        if decision == 'REJECT':
            rejection_reason = 'SCORE_BELOW_THRESHOLD'
        else:
            rejection_reason = None
        
        # Generate full payload
        payload = self._generate_signal_payload(
            ticker, ticker_data, score, decision, rejection_reason
        )
        
        return payload


def main():
    """Main pilot oracle validation."""
    print("WAKE ROBIN BIOTECH ALPHA PILOT ORACLE")
    print("=" * 70)
    print("Validating 7-ticker universe covering all decision paths...")
    print()
    
    # Initialize detector
    detector = PilotDetector()
    as_of_date = date.today()
    
    # [1] Check configuration files
    print("[1] Checking configuration files...")
    config_files = ['tier_weights_v1.yaml', 'thresholds_v1.yaml']
    for config_file in config_files:
        path = os.path.join('config', config_file)
        if os.path.exists(path):
            print(f"   ✅ {config_file}")
        else:
            print(f"   ❌ {config_file} (MISSING)")
    
    # [2] Check source files
    print()
    print("[2] Checking source files...")
    source_files = [
        'src/engine/__init__.py',
        'src/engine/detector.py',
        'tests/pilot/__init__.py',
        'tests/pilot/mock_data_generator.py'
    ]
    
    for source_file in source_files:
        if os.path.exists(source_file):
            print(f"   ✅ {source_file}")
        else:
            print(f"   ⚠️  {source_file} (optional)")
    
    # [3] Running determinism verification
    print()
    print("[3] Running determinism verification...")
    tickers = list(PILOT_UNIVERSE.keys())
    print(f"   ✅ Generated {len(tickers)}-ticker universe: {tickers}")
    
    # Test determinism on first 3 tickers
    for ticker in ['AMGN', 'VRTX', 'AKRO']:
        result1 = detector.process_ticker(ticker, as_of_date, PILOT_UNIVERSE[ticker])
        result2 = detector.process_ticker(ticker, as_of_date, PILOT_UNIVERSE[ticker])
        
        if result1['calc_hash'] == result2['calc_hash']:
            print(f"   ✅ {ticker}: Deterministic")
        else:
            print(f"   ❌ {ticker}: Non-deterministic!")
            print(f"      Hash1: {result1['calc_hash']}")
            print(f"      Hash2: {result2['calc_hash']}")
    
    # [4] Validating expected decisions with detailed output
    print()
    print("[4] Validating expected decisions...")
    
    all_correct = True
    detect_signals = []
    
    for ticker, expected_decision in EXPECTED_DECISIONS.items():
        ticker_data = PILOT_UNIVERSE[ticker]
        result = detector.process_ticker(ticker, as_of_date, ticker_data)
        actual_decision = result['decision']
        
        # Check if decision matches expected
        if actual_decision == expected_decision:
            # Check rejection reason if applicable
            expected_reason = REJECTION_REASONS.get(ticker)
            actual_reason = result.get('rejection_reason')
            
            if expected_reason and actual_reason == expected_reason:
                print(f"   ✅ {ticker}: {actual_decision} ({actual_reason})")
            elif not expected_reason and actual_decision == 'DETECT':
                print(f"   ✅ {ticker}: {actual_decision}")
                # Store DETECT signals for detailed output
                detect_signals.append((ticker, result))
            elif not expected_reason and actual_decision == 'REJECT':
                print(f"   ✅ {ticker}: {actual_decision} ({actual_reason})")
            else:
                print(f"   ⚠️  {ticker}: Decision correct but reason mismatch")
                print(f"      Expected: {expected_reason}")
                print(f"      Got: {actual_reason}")
                all_correct = False
        else:
            print(f"   ❌ {ticker}: Expected {expected_decision}, got {actual_decision}")
            all_correct = False
    
    # Print detailed DETECT signal information
    if detect_signals:
        print()
        print("[5] DETECT Signal Payloads (for Agent 4 integration):")
        print("-" * 70)
        
        for ticker, signal in detect_signals:
            print(f"\n📊 {ticker}:")
            print(f"   Signal ID: {signal['signal_id']}")
            print(f"   Total Score: {signal['total_score']} (Threshold: {signal['threshold']})")
            print(f"   Calculation Hash: {signal['calc_hash']}")
            print(f"   Tier: {signal['tier']}")
            
            # Print component scores
            print("   Component Scores:")
            for component, score in signal['components'].items():
                print(f"     - {component}: {score:.3f}")
            
            # Print metadata
            print("   Metadata:")
            meta = signal['metadata']
            print(f"     - Catalyst Date: {meta.get('catalyst_date', 'N/A')}")
            print(f"     - Probability: {meta.get('probability', 'N/A')}")
            print(f"     - Capital Risk: {meta.get('capital_risk', 'N/A')}")
            
            # Print the exact payload for Agent 4
            print(f"   Agent 4 Payload Key: {signal['signal_id']}")
    
    print()
    print("=" * 70)
    
    if all_correct:
        print("SUCCESS: PILOT ORACLE VALIDATION COMPLETE")
        print("=" * 70)
        print("All 7 tickers produced expected decisions.")
        print()
        print("Next steps:")
        print("1. Review detection scores and signals above")
        print("2. Integrate with existing Agent 4 composite ranker")
        print("3. Deploy to backtest harness")
        print()
        
        # Save DETECT signals to file for Agent 4
        if detect_signals:
            detect_payloads = [signal for _, signal in detect_signals]
            os.makedirs('output', exist_ok=True)
            output_file = f'output/detect_signals_{date.today().isoformat()}.json'
            with open(output_file, 'w') as f:
                json.dump(detect_payloads, f, indent=2)
            print(f"✅ DETECT signals saved to: {output_file}")
        
        return 0
    else:
        print("FAILURE: Pilot oracle validation failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
