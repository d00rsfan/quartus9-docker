"""Test launcher behavior independently of Wine; no Windows code is executed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts/run-quartus.sh"
FAKE_TOOL = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CALL_LOG'], 'a') as stream:
    stream.write(json.dumps(dict(name=name, args=sys.argv[1:],
        prefix=os.environ['WINEPREFIX'], cwd=os.getcwd())) + '\n')
if name == 'xvfb-run':
    os.execvp(sys.argv[4], sys.argv[4:])
if name == 'wineboot':
    Path(os.environ['WINEPREFIX'], 'drive_c').mkdir(parents=True)
if name == 'wine' and sys.argv[1] != 'reg':
    sys.exit(int(os.environ.get('FAKE_STATUS', '0')))
'''


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quartus-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / "bin"
        tools.mkdir()
        install = self.root / "install with spaces"
        (install / "quartus/bin").mkdir(parents=True)
        (install / "quartus/bin/quartus_sh.exe").touch()
        for name in ("wine", "wineboot", "wineserver", "xvfb-run", "xauth"):
            tool = tools / name
            tool.write_text(FAKE_TOOL)
            tool.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.env = dict(os.environ, PATH=str(tools) + ":" + os.environ["PATH"],
                        QUARTUS_INSTALL_DIR=str(install), TMPDIR=str(self.root),
                        CALL_LOG=str(self.log), FAKE_STATUS="0")

    def run_launcher(self, *args):
        return subprocess.run([str(LAUNCHER), *args], cwd=self.root,
                              env=self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_arguments_exit_status_and_cleanup(self):
        self.env["FAKE_STATUS"] = "23"
        result = self.run_launcher("quartus_sh", "--flow", "compile", "a project.qpf")
        self.assertEqual(result.returncode, 23, result.stderr)
        calls = self.calls()
        compile_call = next(c for c in calls if c["name"] == "wine" and c["args"][0] != "reg")
        self.assertEqual(compile_call["args"], ["C:/altera/90sp2/quartus/bin/quartus_sh.exe",
                                              "--flow", "compile", "a project.qpf"])
        self.assertEqual(compile_call["cwd"], str(self.root))
        self.assertFalse(Path(compile_call["prefix"]).exists())
        self.assertTrue(any(c["name"] == "wineserver" and c["args"] == ["-k"] for c in calls))

    def test_default_command(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c["name"] == "wine" and c["args"] == [
            "C:/altera/90sp2/quartus/bin/quartus_sh.exe", "--version"] for c in self.calls()))

    def test_rejects_invalid_command(self):
        self.assertEqual(self.run_launcher("../../unexpected").returncode, 64)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
