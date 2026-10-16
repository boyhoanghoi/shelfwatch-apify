import argparse
import asyncio
import json
import os
from pathlib import Path

from .config import RunConfig
from .output import export_results
from .runner import run_pipeline
from .state import MAX_STATE_BYTES, write_atomic


def main():
    parser = argparse.ArgumentParser(description="ShelfWatch: repeat Shopify price/restock checks with a local state checkpoint.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/local"))
    parser.add_argument("--state-file", type=Path, default=Path("output/shelfwatch-state.json"))
    args = parser.parse_args()
    lock = None
    try:
        if args.input.stat().st_size > 128 * 1024:
            raise ValueError("Input exceeds 128 KiB.")
        config = RunConfig.from_dict(json.loads(args.input.read_text(encoding="utf-8-sig")))
        state_path = args.state_file.resolve()
        outputs = {args.output.resolve() / name for name in ("results.json", "alerts.json", "summary.json", "diagnostics.json", "checks.csv", "alerts.csv", "alerts.ndjson", "digest.md")}
        if state_path == args.input.resolve() or state_path in outputs:
            raise ValueError("State checkpoint must not overwrite input or an export file.")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        lock = state_path.with_name(state_path.name + ".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            lock = None
            raise ValueError("State file is locked by another run. After a crashed run, remove its .lock file only when no process uses it.") from None
        os.close(descriptor)
        state = {"version": 1, "monitorName": config.monitor_name, "products": {}}
        if state_path.exists():
            if state_path.stat().st_size > MAX_STATE_BYTES:
                raise ValueError("State file exceeds 8 MiB.")
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
            if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1 or state.get("monitorName") != config.monitor_name or not isinstance(state.get("products"), dict):
                raise ValueError("State version/monitorName does not match this run.")
        async def load(key):
            return state["products"].get(key)
        async def save(row, current):
            state["products"][row["productKey"]] = current
            return True
        report = asyncio.run(run_pipeline(config, load, save))
        export_results(report, args.output)
        write_atomic(state_path, state)
    except (OSError, ValueError, RecursionError) as exc:
        parser.exit(2, f"ShelfWatch: {exc}\n")
    finally:
        if lock is not None:
            lock.unlink(missing_ok=True)
    print(f"Saved {len(report['results'])} checks and {len(report['alerts'])} observations to {args.output.resolve()}.")
    return 1 if report["summary"]["failedProducts"] and not report["results"] else 0
