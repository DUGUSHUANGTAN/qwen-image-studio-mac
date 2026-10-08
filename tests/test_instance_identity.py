"""A Mac window must be able to distinguish its store from another local Studio."""
import json
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstanceIdentityTest(unittest.TestCase):
    def test_config_identifies_its_data_directory(self):
        with tempfile.TemporaryDirectory() as data:
            with open(Path(data) / "server.log", "w") as log:
                proc = subprocess.Popen([
                    str(ROOT / "app/.venv/bin/python"), str(ROOT / "app/web/server.py"),
                    "--port", "18731", "--data-dir", data,
                ], stdout=log, stderr=log)
                try:
                    for _ in range(40):
                        try:
                            result = json.load(urllib.request.urlopen("http://127.0.0.1:18731/api/config"))
                            break
                        except Exception:
                            time.sleep(.2)
                    else:
                        self.fail("server did not start")
                    self.assertEqual(result.get("data_dir"), str(Path(data).resolve()))
                finally:
                    proc.terminate()
                    proc.wait(timeout=8)


if __name__ == "__main__":
    unittest.main()
