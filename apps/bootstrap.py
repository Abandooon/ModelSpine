"""Local checkout entrypoints; no installation or external source paths."""
import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
for package in ("protocols", "model-kernel", "assurance", "generation"):
    sys.path.insert(0, str(PLATFORM / "packages" / package / "src"))
sys.path.insert(0, str(PLATFORM / "apps"))
