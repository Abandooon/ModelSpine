"""Verify runtime imports with only the package and its current runtime dependency."""
import ast
import subprocess
import sys
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[1]
PACKAGES = {
    "protocols": "modelspine_protocols",
    "model-kernel": "modelspine_kernel",
    "assurance": "modelspine_assurance",
    "generation": "modelspine_generation",
    "requirements": "modelspine_requirements",
}


class PackageBoundaryTests(unittest.TestCase):
    def test_finite_model_adapter_imports_with_only_protocols(self):
        paths = [str(PLATFORM / 'packages' / 'protocols' / 'src'), str(PLATFORM / 'adapters')]
        script = (f"import sys; sys.path[:0]={paths!r}; import finite_models; "
                  "import task_checks; loaded={name for name in sys.modules if name.startswith('modelspine_')}; "
                  "assert loaded == {'modelspine_protocols'}, loaded")
        result = subprocess.run([sys.executable, '-B', '-I', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_packages_import_without_other_capabilities_or_application_paths(self):
        for package, module in PACKAGES.items():
            with self.subTest(package=package):
                paths = [str(PLATFORM / "packages" / name / "src")
                         for name in dict.fromkeys(("protocols", package))]
                expected = {"modelspine_protocols", module}
                script = (f"import sys; sys.path[:0]={paths!r}; import {module}; "
                          "loaded={name for name in sys.modules if name.startswith('modelspine_')}; "
                          f"assert loaded == {expected!r}, loaded")
                result = subprocess.run([sys.executable, "-B", "-I", "-c", script],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_assessment_imports_without_kernel_adapter_or_application(self):
        paths = [str(PLATFORM / "packages" / name / "src") for name in ("protocols", "assurance")]
        script = (f"import sys; sys.path[:0]={paths!r}; import modelspine_assurance.tasks; "
                  "assert 'modelspine_kernel' not in sys.modules; "
                  "assert 'task_checks' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_application_does_not_load_reference_evaluator(self):
        paths = [str(PLATFORM / "apps")]
        script = (f"import sys; sys.path[:0]={paths!r}; import task_acceptance; import clarification; import bounded_generation; "
                  "assert not any('oracle' in name or name.startswith('support') for name in sys.modules)")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bounded_search_and_adapter_only_need_generation_and_protocols(self):
        paths = [str(PLATFORM / "packages" / name / "src") for name in ("protocols", "generation")]
        paths.append(str(PLATFORM / "adapters"))
        script = (f"import sys; sys.path[:0]={paths!r}; import modelspine_generation.bounded; "
                  "import dag_construction; assert 'modelspine_kernel' not in sys.modules; "
                  "assert 'task_checks' not in sys.modules; assert 'bounded_generation' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_clarification_adapter_has_no_kernel_or_application_dependency(self):
        paths = [str(PLATFORM / "packages" / name / "src") for name in ("protocols", "requirements")]
        paths.append(str(PLATFORM / "adapters"))
        script = (f"import sys; sys.path[:0]={paths!r}; import clarification_checks; "
                  "assert 'modelspine_kernel' not in sys.modules; "
                  "assert 'clarification' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-I", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_imports_stay_within_standard_library_and_protocols(self):
        for package, module in PACKAGES.items():
            allowed = sys.stdlib_module_names | {module, "modelspine_protocols"}
            for source in (PLATFORM / "packages" / package / "src").rglob("*.py"):
                with self.subTest(source=source):
                    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                        if isinstance(node, ast.Import):
                            imports = [alias.name.split(".")[0] for alias in node.names]
                        elif isinstance(node, ast.ImportFrom) and node.level == 0:
                            imports = [node.module.split(".")[0]]
                        else:
                            continue
                        self.assertTrue(set(imports) <= allowed, (source, imports))


if __name__ == "__main__":
    unittest.main()
