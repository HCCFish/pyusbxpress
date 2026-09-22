import os
import re
import unittest

import usbxpress

_PYPROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "pyproject.toml")


class VersionTests(unittest.TestCase):
    def test_version_matches_pyproject(self):
        """__version__ and the packaged version must not drift apart."""
        with open(_PYPROJECT, "r", encoding="utf-8") as handle:
            text = handle.read()
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match, "version not found in pyproject.toml")
        self.assertEqual(usbxpress.__version__, match.group(1))


if __name__ == "__main__":
    unittest.main()
