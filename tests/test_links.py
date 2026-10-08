import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('check_links', Path(__file__).resolve().parents[1] / 'scripts/check_links.py')
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class LinkTests(unittest.TestCase):
    def test_broken_links_anchors_and_file_references_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('[missing](missing.md)\n[anchor](target.md#absent)\n[ref][undefined]\nRead `scripts/missing.py`.\n')
            (root / 'target.md').write_text('# Present\n')
            _, _, errors = links.check(root)
            self.assertEqual(len(errors), 4)

    def test_relative_encoded_paths_reference_links_and_duplicate_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'target file.md').write_text('# Hello\n# Hello\n')
            (root / 'docs/page.md').write_text('[valid](../target%20file.md#hello-1)\n[valid][target]\n[target]: ../target%20file.md#hello\n')
            self.assertEqual(links.check(root)[2], [])


if __name__ == '__main__':
    unittest.main()
