"""Run isolated package units and the explicit cross-package integration suite."""
import argparse
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps"))
import bootstrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--package", choices=bootstrap.PACKAGES)
    selection.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    if not args.package and not args.integration:
        commands = [["--package", package] for package in bootstrap.PACKAGES] + [["--integration"]]
        results = [subprocess.run([sys.executable, "-B", "-I", str(Path(__file__).resolve()), *command])
                   for command in commands]
        return 0 if all(result.returncode == 0 for result in results) else 1
    bootstrap.activate((args.package,) if args.package else bootstrap.PACKAGES)
    folder = (bootstrap.PLATFORM / "packages" / args.package / "tests"
              if args.package else bootstrap.PLATFORM / "tests")
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().discover(str(folder), top_level_dir=str(folder)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
