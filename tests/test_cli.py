import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shelfwatch.cli import main
from shelfwatch.runner import run_pipeline
from test_core import FakeClient, URL


class CliTests(unittest.TestCase):
    async def pipeline(self, config, load, save):
        return await run_pipeline(config, load, save, client_factory=FakeClient)

    def test_checkpoint_is_reused_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps({"productUrls": [URL]}))
            state = root / "state.json"
            for number in (1, 2):
                output = root / str(number)
                args = ["shelfwatch", "--input", str(source), "--output", str(output), "--state-file", str(state)]
                with patch("sys.argv", args), patch("shelfwatch.cli.run_pipeline", self.pipeline), patch("builtins.print"):
                    self.assertEqual(main(), 0)
                summary = json.loads((output / "summary.json").read_text())
                self.assertEqual(summary["savedChecks"], 1)
                self.assertEqual(summary["alertCount"], 1 if number == 1 else 0)
                self.assertFalse(state.with_name("state.json.lock").exists())

    def test_export_failure_does_not_promote_checkpoint_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, state = root / "input.json", root / "state.json"
            source.write_text(json.dumps({"productUrls": [URL]}))
            old = {"version": 1, "monitorName": "my-watchlist", "products": {}}
            state.write_text(json.dumps(old))
            args = ["shelfwatch", "--input", str(source), "--output", str(root / "output"), "--state-file", str(state)]
            with patch("sys.argv", args), patch("shelfwatch.cli.run_pipeline", self.pipeline), patch("shelfwatch.cli.export_results", side_effect=OSError("Disk full")), self.assertRaises(SystemExit):
                main()
            self.assertEqual(json.loads(state.read_text()), old)
            self.assertFalse(state.with_name("state.json.lock").exists())
