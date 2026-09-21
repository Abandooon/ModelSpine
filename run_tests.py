"""Offline behavioral checks across the four exercised packages."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps"))
import bootstrap


if __name__ == "__main__":
    suite = unittest.TestSuite()
    for package in ("protocols", "model-kernel", "assurance", "generation"):
        folder = bootstrap.PLATFORM / "packages" / package / "tests"
        suite.addTests(unittest.TestLoader().discover(str(folder), top_level_dir=str(folder)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
