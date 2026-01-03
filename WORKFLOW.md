# Biotech Alpha System — Working Directory

## Quickstart
```bash
python -m pip install -r requirements.txt
pytest -q
python run_pipeline.py --as-of 2024-01-01
```

## Fixture policy (production rule)
- Network calls are allowed ONLY in: `src/data/fixtures_builder.py` and `src/data/source_clients/*`
- Production agents must read frozen fixtures under: `fixtures/asof=YYYY-MM-DD/`

## Git workflow (recommended)
- main: stable, tagged releases
- dev: feature work
- Each change: PR + tests must pass (`pytest -q`)
