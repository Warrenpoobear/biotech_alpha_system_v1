# Biotech Alpha System — SYSTEM_STATE (v1)

## Contracts (non-negotiable)
- **Determinism**: identical inputs => identical outputs (byte-for-byte) for all artifacts
- **Fail-Loud**: missing required data => explicit suppression/quarantine; never silent defaults
- **Provenance**: every output field traces to a source ref + (optional) extraction timestamp
- **Point-in-Time (PIT)**: no `now()`/network in production runs; inputs must be fixtures frozen at `as_of`
- **IC-Ready**: outputs must include drivers, risks, and provenance sufficient for committee defense

## Versions
- Schema version: `v1`
- Determinism contract: `v1`
- Package: `biotech_alpha_system` (local)

## Entry points
- `python run_pipeline.py --as-of YYYY-MM-DD --universe-version v1 --weights-version v1`

## Added in v1-e2e+
- Fixtures builder CLI: `python scripts/build_fixtures.py --as-of YYYY-MM-DD --demo`
- Dossier generator: deterministic IC memo output to `artifacts/dossiers/`
