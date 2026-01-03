# {ticker} — IC Memo (as_of={as_of})

## 1. Executive Summary
**Composite Score:** {composite_score:.1f}/100  
**Primary Driver:** {primary_driver}  
**Next Catalyst:** {next_catalyst_desc} (in {next_catalyst_days} days)

## 2. Investment Thesis (Why Now)
- {thesis_bullet_1}
- {thesis_bullet_2}
- {thesis_bullet_3}

## 3. Evidence Packet Summary
**Trial Design Quality:** {design_quality:.2f}  
**Probability of Success:** {pos:.2f}  
**rNPV (v1):** ${rnpv_usd:,.0f}

## 4. Key Risks
- Dilution risk (90d): {dilution_risk:.2f}
- Binary risk (90d): {binary_risk:.2f}
- Suppressions: {suppressions}

## 5. Kill Criteria (Explicit)
- Catalyst misses timeline by >{kill_slip_days} days without credible explanation
- Major safety signal / protocol change increasing failure risk materially
- Financing terms meaningfully worse than expected (dilution > threshold)

## 6. Position Sizing (Heuristic)
**Suggested size:** {position_size_bps} bps  
**Rationale:** {sizing_rationale}

## 7. Provenance
{provenance_lines}
