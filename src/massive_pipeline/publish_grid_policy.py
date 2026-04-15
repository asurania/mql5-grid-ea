from __future__ import annotations

from pathlib import Path
import shutil
import json

ROOT = Path(__file__).resolve().parents[2]
SRC_FILE = ROOT / "data" / "live" / "policy" / "grid_policy.json"
DST_FILE = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave" / "grid_policy.json"


def main() -> int:
    if not SRC_FILE.exists():
        raise SystemExit(f"missing source grid policy: {SRC_FILE}")

    DST_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_FILE, DST_FILE)

    payload = json.loads(SRC_FILE.read_text(encoding="utf-8"))
    summary = {
        "status": "ok",
        "source": str(SRC_FILE.relative_to(ROOT)),
        "destination": str(DST_FILE.relative_to(ROOT)),
        "version": payload.get("version"),
        "model": payload.get("model"),
        "pair_rows": len(payload.get("pairs", [])),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
