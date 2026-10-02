"""Local checkout entrypoints; no installation or external source paths."""
import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
PACKAGES = ("protocols", "model-kernel", "assurance", "generation", "requirements", "interaction", "implementation")


def activate(packages):
    """Expose requested packages and their explicit current runtime dependencies."""
    if any(package not in PACKAGES for package in packages):
        raise ValueError("unknown runtime package")
    # The finite materializer consumes the finite generation plan/render contract.
    dependencies = ("generation",) if "implementation" in packages else ()
    for package in dict.fromkeys(("protocols", *packages, *dependencies)):
        source = str(PLATFORM / "packages" / package / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
