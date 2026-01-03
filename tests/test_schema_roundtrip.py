from datetime import date, datetime
from src.schemas.common import PacketMeta
from src.schemas.science_packet import SciencePacket, TrialPhase, Catalyst, CatalystType

def test_science_packet_validates():
    meta = PacketMeta(packet_type="science", run_id="r1", as_of="2024-01-01", generator="test", code_version="local")
    pkt = SciencePacket(
        meta=meta,
        packet_id="AAA_2024-01-01",
        as_of=date(2024,1,1),
        extraction_timestamp="2024-01-01T00:00:00Z",
        ticker="AAA",
        drug_name="DrugX",
        indication="Oncology",
        trial_id="NCT12345678",
        phase=TrialPhase.phase2,
        primary_endpoint="PFS",
        catalysts=[Catalyst(type=CatalystType.topline_results, date=date(2024,6,1), description="Phase 2 topline", impact_tier=2, source="fixture")],
        source_urls=["file://fixture"],
        extraction_confidence=0.5,
        suppression_flags=[],
        data_quality_score=0.6,
    )
    assert pkt.ticker == "AAA"
