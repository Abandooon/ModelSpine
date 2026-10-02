import tempfile
from pathlib import Path
import unittest

from modelspine_protocols import ContractError
from modelspine_implementation.local_runtime import exclusive, safe_path
from modelspine_implementation.local_web import _paths_do_not_overlap


class DeliveryBoundaryTests(unittest.TestCase):
    def test_windows_aliases_and_relative_escape_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("../escape", "C:/escape", "a\\b", "CON.json", "a/../b", "a./b", "a:b", "a?/b"):
                with self.subTest(name=name), self.assertRaises(ContractError):
                    safe_path(root,name)
            self.assertEqual(list(root.iterdir()),[])

    def test_cross_platform_collision_and_process_lock(self):
        for names in (("data.json","DATA.JSON"),("modelspine_protocols","modelspine_protocols/__init__.py")):
            with self.assertRaises(ContractError): _paths_do_not_overlap(names)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with exclusive(root):
                with self.assertRaises(ContractError) as error:
                    with exclusive(root): pass
                self.assertEqual(error.exception.code,"busy")
            self.assertEqual(list(root.iterdir()),[])
