"""Guard: BM_DEMO_FILE env dirige get_demo_file sin tocar canónico."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestBmDemoFileEnv(unittest.TestCase):
    def test_env_override(self) -> None:
        from app.core.storage import demo_files

        demo_files.set_demo_file_override(None)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "alt.json"
            target.write_text("{}", encoding="utf-8")
            prev = os.environ.get("BM_DEMO_FILE")
            try:
                os.environ["BM_DEMO_FILE"] = str(target)
                self.assertEqual(demo_files.get_demo_file(), target.resolve())
            finally:
                if prev is None:
                    os.environ.pop("BM_DEMO_FILE", None)
                else:
                    os.environ["BM_DEMO_FILE"] = prev
                demo_files.set_demo_file_override(None)


if __name__ == "__main__":
    unittest.main()
