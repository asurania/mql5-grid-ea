#!/usr/bin/env python3
"""Start the ForexSlave dashboard backend server."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "dashboard" / "backend"))

# Force trading_config to use the workspace root
import massive_pipeline.trading_config as tc
tc.ROOT = ROOT
tc.CONFIG_FILE = ROOT / "config" / "trading_config.json"

import uvicorn
from main import app

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8081, reload=True, reload_dirs=[str(ROOT / "src" / "dashboard" / "backend")])