"""Mock data generator for 7-ticker pilot oracle."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict


@dataclass
class MockTickerData:
    """Complete mock data for a single ticker."""
    ticker: str
    price: float
    shares_millions: float
    market_cap_millions: float
    phase: str
    catalyst_date: date
    days_to_catalyst: int
    cash_millions: float
    probability_of_success: float
    catalyst_verified: bool
    catalyst_source: str
    expected_decision: str
    expected_rejection_reasons: list
    upside_potential: float = 2.0
    downside_risk: float = 0.3
    runway_months: int = 18
    short_interest_pct: float = 5.0
    momentum_21d: float = 0.05


class PilotOracleDataGenerator:
    """Generates the canonical 7-ticker test universe."""
    
    @staticmethod
    def generate_universe(as_of_date: date = date(2024, 1, 1)) -> Dict[str, MockTickerData]:
        """Generate the complete 7-ticker test universe."""
        def days_ahead(days: int) -> date:
            return as_of_date + timedelta(days=days)
        
        return {
            'AMGN': MockTickerData(
                ticker='AMGN', price=280.50, shares_millions=530, market_cap_millions=148_665,
                phase='Phase_3', catalyst_date=days_ahead(180), days_to_catalyst=180,
                cash_millions=8_500, probability_of_success=0.65, catalyst_verified=True,
                catalyst_source='clinicaltrials.gov|NCT12345678', expected_decision='DETECT',
                expected_rejection_reasons=[], upside_potential=1.4, downside_risk=0.25,
                runway_months=36, short_interest_pct=3.0, momentum_21d=0.08
            ),
            'VRTX': MockTickerData(
                ticker='VRTX', price=420.75, shares_millions=262, market_cap_millions=110_237,
                phase='NDA', catalyst_date=days_ahead(120), days_to_catalyst=120,
                cash_millions=12_800, probability_of_success=0.85, catalyst_verified=True,
                catalyst_source='sec.gov|8-K|2024-01-01', expected_decision='DETECT',
                expected_rejection_reasons=[], upside_potential=1.3, downside_risk=0.20,
                runway_months=48, short_interest_pct=2.5, momentum_21d=0.12
            ),
            'AKRO': MockTickerData(
                ticker='AKRO', price=8.25, shares_millions=45, market_cap_millions=371,
                phase='Phase_2', catalyst_date=days_ahead(90), days_to_catalyst=90,
                cash_millions=85, probability_of_success=0.35, catalyst_verified=False,
                catalyst_source='company_website|press_release', expected_decision='REJECT',
                expected_rejection_reasons=['CATALYST_UNVERIFIED'], upside_potential=3.5,
                downside_risk=0.60, runway_months=14, short_interest_pct=12.0, momentum_21d=-0.05
            ),
            'MISSING': MockTickerData(
                ticker='MISSING', price=None, shares_millions=None, market_cap_millions=None,
                phase=None, catalyst_date=None, days_to_catalyst=0, cash_millions=None,
                probability_of_success=0.0, catalyst_verified=False, catalyst_source='',
                expected_decision='REJECT', expected_rejection_reasons=['DATA_INSUFFICIENT'],
                upside_potential=0.0, downside_risk=0.0, runway_months=0,
                short_interest_pct=0.0, momentum_21d=0.0
            ),
            'EARLY': MockTickerData(
                ticker='EARLY', price=15.60, shares_millions=35, market_cap_millions=546,
                phase='Phase_3', catalyst_date=days_ahead(20), days_to_catalyst=20,
                cash_millions=120, probability_of_success=0.60, catalyst_verified=True,
                catalyst_source='clinicaltrials.gov|NCT99999999', expected_decision='REJECT',
                expected_rejection_reasons=['TIMING_UNSUITABLE'], upside_potential=2.8,
                downside_risk=0.40, runway_months=18, short_interest_pct=8.0, momentum_21d=0.15
            ),
            'LOWPOS': MockTickerData(
                ticker='LOWPOS', price=12.30, shares_millions=40, market_cap_millions=492,
                phase='Phase_1', catalyst_date=days_ahead(60), days_to_catalyst=60,
                cash_millions=95, probability_of_success=0.15, catalyst_verified=True,
                catalyst_source='clinicaltrials.gov|NCT11111111', expected_decision='REJECT',
                expected_rejection_reasons=['PROBABILITY_TOO_LOW'], upside_potential=5.0,
                downside_risk=0.70, runway_months=16, short_interest_pct=15.0, momentum_21d=-0.10
            ),
            'RISKY': MockTickerData(
                ticker='RISKY', price=6.80, shares_millions=30, market_cap_millions=204,
                phase='Phase_2', catalyst_date=days_ahead(150), days_to_catalyst=150,
                cash_millions=22, probability_of_success=0.40, catalyst_verified=True,
                catalyst_source='clinicaltrials.gov|NCT22222222', expected_decision='REJECT',
                expected_rejection_reasons=['CAPITAL_RISK_HIGH'], upside_potential=4.0,
                downside_risk=0.80, runway_months=6, short_interest_pct=18.0, momentum_21d=-0.20
            ),
        }
