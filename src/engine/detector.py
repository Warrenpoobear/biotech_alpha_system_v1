"""
Minimal WakeRobinDetector for pilot oracle testing.
"""
import hashlib
import json
from datetime import date
from typing import Dict, Any


class WakeRobinDetector:
    """Minimal detector for pilot testing."""
    
    def __init__(self, config_path: str = None):
        self.config = self.load_config(config_path)
        self.detection_threshold = 0.70
    
    @staticmethod
    def load_config(config_path: str = None) -> Dict[str, Any]:
        """Load configuration from YAML."""
        if config_path and config_path.endswith('tier_weights_v1.yaml'):
            return {
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
        return {}
    
    @classmethod
    def from_default_config(cls):
        """Create detector with default config."""
        return cls('config/tier_weights_v1.yaml')
    
    def process_ticker(self, ticker: str, as_of_date: date, mock_data = None):
        """Process a ticker through the decision pipeline."""
        if mock_data is None:
            return {'error': 'No mock data provided'}
        
        tier = self._determine_tier(mock_data)
        kill_switch_result = self._apply_kill_switches(mock_data, tier)
        
        if not kill_switch_result['passed']:
            return self._format_rejection(mock_data, tier, kill_switch_result)
        
        signals = self._compute_signals(mock_data, tier)
        total_score = self._calculate_weighted_score(signals, tier)
        
        if total_score >= self.detection_threshold:
            return self._format_detection(mock_data, tier, signals, total_score)
        else:
            return self._format_score_rejection(mock_data, tier, signals, total_score)
    
    def _determine_tier(self, mock_data):
        """Determine tier based on market cap."""
        if mock_data.market_cap_millions is None:
            return 'unknown'
        return 'tier1' if mock_data.market_cap_millions >= 5000 else 'tier2'
    
    def _apply_kill_switches(self, mock_data, tier: str):
        """Apply kill switches in priority order."""
        rejection_reasons = []
        
        if mock_data.price is None or mock_data.shares_millions is None:
            rejection_reasons.append('DATA_INSUFFICIENT')
            return {'passed': False, 'reasons': rejection_reasons}
        
        if mock_data.days_to_catalyst < 30 or mock_data.days_to_catalyst > 365:
            rejection_reasons.append('TIMING_UNSUITABLE')
            return {'passed': False, 'reasons': rejection_reasons}
        
        if mock_data.probability_of_success < 0.25:
            rejection_reasons.append('PROBABILITY_TOO_LOW')
            return {'passed': False, 'reasons': rejection_reasons}
        
        if tier == 'tier2' and mock_data.runway_months < 12:
            rejection_reasons.append('CAPITAL_RISK_HIGH')
            return {'passed': False, 'reasons': rejection_reasons}
        
        if not mock_data.catalyst_verified:
            rejection_reasons.append('CATALYST_UNVERIFIED')
            return {'passed': False, 'reasons': rejection_reasons}
        
        return {'passed': True, 'reasons': []}
    
    def _compute_signals(self, mock_data, tier: str):
        """Compute simplified signals for pilot."""
        if 30 <= mock_data.days_to_catalyst <= 90:
            catalyst_setup = 0.9
        elif 90 < mock_data.days_to_catalyst <= 180:
            catalyst_setup = 0.7
        elif 180 < mock_data.days_to_catalyst <= 365:
            catalyst_setup = 0.5
        else:
            catalyst_setup = 0.3
        
        probability_of_success = mock_data.probability_of_success
        payoff_asymmetry = min(1.0, mock_data.upside_potential / (1 + mock_data.downside_risk))
        
        if mock_data.runway_months >= 24:
            capital_risk = 0.9
        elif mock_data.runway_months >= 12:
            capital_risk = 0.7
        elif mock_data.runway_months >= 6:
            capital_risk = 0.4
        else:
            capital_risk = 0.1
        
        data_coverage = 0.0 if mock_data.ticker == 'MISSING' else 1.0
        
        sentiment_base = 0.5 + (mock_data.momentum_21d * 2)
        sentiment_adjusted = sentiment_base * (1 - min(0.5, mock_data.short_interest_pct / 40))
        positioning_sentiment = max(0.0, min(1.0, sentiment_adjusted))
        
        return {
            'catalyst_setup': round(catalyst_setup, 4),
            'probability_of_success': round(probability_of_success, 4),
            'payoff_asymmetry': round(payoff_asymmetry, 4),
            'capital_risk': round(capital_risk, 4),
            'data_coverage': round(data_coverage, 4),
            'positioning_sentiment': round(positioning_sentiment, 4)
        }
    
    def _calculate_weighted_score(self, signals, tier: str):
        """Calculate weighted score based on tier."""
        if tier == 'tier1':
            weights = self.config.get('tier1_weights', {
                'catalyst_setup': 0.15, 'probability_of_success': 0.15,
                'payoff_asymmetry': 0.20, 'capital_risk': 0.10,
                'data_coverage': 0.05, 'positioning_sentiment': 0.35
            })
        else:
            weights = self.config.get('tier2_weights', {
                'catalyst_setup': 0.25, 'probability_of_success': 0.25,
                'payoff_asymmetry': 0.20, 'capital_risk': 0.15,
                'data_coverage': 0.05, 'positioning_sentiment': 0.10
            })
        
        total_score = sum(signals[key] * weight for key, weight in weights.items())
        return round(total_score, 4)
    
    def _format_rejection(self, mock_data, tier: str, kill_switch_result):
        """Format rejection result."""
        return {
            'ticker': mock_data.ticker,
            'as_of_date': date(2024, 1, 1).isoformat(),
            'decision': 'REJECT',
            'tier': tier,
            'market_cap_millions': mock_data.market_cap_millions,
            'kill_switches_passed': False,
            'rejection_reasons': kill_switch_result['reasons'],
            'primary_rejection_reason': kill_switch_result['reasons'][0] if kill_switch_result['reasons'] else None,
            'total_score': None,
            'signals': None,
            'calc_hash': self._calculate_hash(mock_data, tier, kill_switch_result),
            'full_hash': self._calculate_full_hash(mock_data, tier, kill_switch_result)
        }
    
    def _format_detection(self, mock_data, tier: str, signals, total_score: float):
        """Format detection result."""
        formatted_signals = {k: f"{v:.4f}" for k, v in signals.items()}
        return {
            'ticker': mock_data.ticker,
            'as_of_date': date(2024, 1, 1).isoformat(),
            'decision': 'DETECT',
            'tier': tier,
            'market_cap_millions': mock_data.market_cap_millions,
            'kill_switches_passed': True,
            'rejection_reasons': [],
            'primary_rejection_reason': None,
            'total_score': f"{total_score:.4f}",
            'signals': formatted_signals,
            'calc_hash': self._calculate_hash(mock_data, tier, {'passed': True}, signals, total_score),
            'full_hash': self._calculate_full_hash(mock_data, tier, {'passed': True}, signals, total_score)
        }
    
    def _format_score_rejection(self, mock_data, tier: str, signals, total_score: float):
        """Format rejection due to low score."""
        formatted_signals = {k: f"{v:.4f}" for k, v in signals.items()}
        return {
            'ticker': mock_data.ticker,
            'as_of_date': date(2024, 1, 1).isoformat(),
            'decision': 'REJECT',
            'tier': tier,
            'market_cap_millions': mock_data.market_cap_millions,
            'kill_switches_passed': True,
            'rejection_reasons': ['SCORE_BELOW_THRESHOLD'],
            'primary_rejection_reason': 'SCORE_BELOW_THRESHOLD',
            'total_score': f"{total_score:.4f}",
            'signals': formatted_signals,
            'calc_hash': self._calculate_hash(mock_data, tier, {'passed': True}, signals, total_score),
            'full_hash': self._calculate_full_hash(mock_data, tier, {'passed': True}, signals, total_score)
        }
    
    def _calculate_hash(self, mock_data, tier: str, kill_switch_result, signals=None, total_score=None):
        """Calculate deterministic hash for result."""
        hash_data = {
            'ticker': mock_data.ticker,
            'as_of_date': '2024-01-01',
            'tier': tier,
            'kill_switch_passed': kill_switch_result['passed'],
            'rejection_reasons': kill_switch_result.get('reasons', [])
        }
        
        if signals:
            hash_data['signals'] = {k: f"{v:.4f}" for k, v in signals.items()}
            hash_data['total_score'] = f"{total_score:.4f}" if total_score else None
        
        json_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def _calculate_full_hash(self, mock_data, tier: str, kill_switch_result, signals=None, total_score=None):
        """Calculate full hash with additional metadata."""
        calc_hash = self._calculate_hash(mock_data, tier, kill_switch_result, signals, total_score)
        full_data = {
            'calc_hash': calc_hash,
            'engine_version': 'pilot_v1.0',
            'config_version': 'tier_weights_v1.0',
            'detection_threshold': self.detection_threshold
        }
        json_str = json.dumps(full_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
