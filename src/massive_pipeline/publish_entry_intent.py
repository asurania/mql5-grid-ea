from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILE = ROOT / "data" / "live" / "policy" / "entry_intent.json"
HANDOFF_DIR = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave"
RUN_LOG = ROOT / "data" / "live" / "policy" / "publish_entry_intent_run.json"


def main() -> int:
    started = datetime.now(timezone.utc)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_FILE.exists():
        payload = {
            "status": "failed",
            "started_at_utc": started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": f"missing source intent: {SOURCE_FILE}",
        }
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    dest = HANDOFF_DIR / "entry_intent.json"
    shutil.copy2(SOURCE_FILE, dest)

    payload = {
        "status": "ok",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_intent": str(SOURCE_FILE.relative_to(ROOT)),
        "published_intent": str(dest.relative_to(ROOT)),
    }
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
