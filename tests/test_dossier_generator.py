from datetime import date
from pathlib import Path
from src.output.dossier_generator import DossierGenerator
from src.schemas.screen_results import ScreenResult
from src.schemas.common import PacketMeta
from src.schemas.science_packet import SciencePacket, TrialPhase
from src.schemas.pos_packet import PoSPacket, PoSAdjustment
from src.schemas.rnpv_packet import RNPVPacket, Scenario, ScenarioName
from src.schemas.market_packet import MarketPacket

def test_dossier_deterministic(tmp_path: Path):
    meta = PacketMeta(packet_type="science", run_id="r1", as_of="2024-01-01", generator="t", code_version="local")
    sp = SciencePacket(
        meta=meta, packet_id="s1", as_of=date(2024,1,1), extraction_timestamp="PIT",
        ticker="AAA", drug_name="DrugX", indication="oncology", trial_id="NCT12345678",
        phase=TrialPhase.phase2, primary_endpoint="PFS", extraction_confidence=0.5,
        suppression_flags=[], data_quality_score=0.6, source_urls=["fixture://x"]
    )
    pp = PoSPacket(
        meta=PacketMeta(packet_type="pos", run_id="r1", as_of="2024-01-01", generator="t", code_version="local"),
        packet_id="p1", ticker="AAA", base_rate=0.25, final_pos=0.30, confidence_interval=[0.24,0.36],
        adjustments=[PoSAdjustment(name="design_quality", delta=0.01, rationale="x")], key_drivers=["design_quality"]
    )
    rp = RNPVPacket(
        meta=PacketMeta(packet_type="rnpv", run_id="r1", as_of="2024-01-01", generator="t", code_version="local"),
        packet_id="r1", ticker="AAA", total_rnpv_usd=1_000_000.0,
        scenarios=[Scenario(name=ScenarioName.base, probability=1.0, revenue_peak_usd=1.0, margin=0.6, discount_rate=0.1, years_to_peak=3)]
    )
    mp = MarketPacket(
        meta=PacketMeta(packet_type="market", run_id="r1", as_of="2024-01-01", generator="t", code_version="local"),
        packet_id="m1", ticker="AAA", close=10.0, volume=1000.0, adv_usd=10000.0, short_interest_pct=None
    )
    sr = ScreenResult(
        ticker="AAA", company_name="Alpha", as_of=date(2024,1,1),
        composite_score=55.0, science_score=50.0, pos_score=30.0, valuation_score=40.0, setup_score=20.0,
        primary_driver="science", secondary_drivers=["valuation"], suppression_flags=[],
        next_catalyst_days=None, next_catalyst_type=None, catalyst_impact_tier=None,
        dilution_risk_90d=0.4, binary_event_risk_90d=0.3,
        science_packet_id="s1", pos_packet_id="p1", rnpv_packet_id="r1", market_packet_id="m1"
    )

    dg = DossierGenerator()
    out1 = tmp_path/"m1.md"
    out2 = tmp_path/"m2.md"
    dg.generate_one(sr, sp, pp, rp, mp, run_id="r1", out_path=out1)
    dg.generate_one(sr, sp, pp, rp, mp, run_id="r1", out_path=out2)
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
