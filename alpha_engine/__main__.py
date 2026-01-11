"""Allow running alpha_engine as a module.

Usage:
    python -m alpha_engine --as-of-date 2024-01-15 --input-dir screener_outputs/
"""

import sys
from alpha_engine.run import main

if __name__ == "__main__":
    sys.exit(main())
