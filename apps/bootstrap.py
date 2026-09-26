"""Local checkout entrypoints; no installation or external source paths."""
import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
PACKAGES = ("protocols", "model-kernel", "assurance", "generation", "requirements")


def activate(packages):
    """Expose only requested packages and their current shared protocol dependency."""
    if any(package not in PACKAGES for package in packages):
        raise ValueError("unknown runtime package")
    for package in dict.fromkeys(("protocols", *packages)):
        source = str(PLATFORM / "packages" / package / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
