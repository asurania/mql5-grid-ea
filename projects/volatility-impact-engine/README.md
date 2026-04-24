# Volatility Impact Engine

Notebook-first prototype for an ML-driven volatility impact engine that combines:

- Economic calendar event feeds
- Massive.com granular forex data
- Realized-volatility labeling around event windows
- A PyTorch model that predicts dynamic event impact scores per symbol

## Current status

- Jupyter notebook scaffold created
- CPU-first execution path works now
- Structured for later ROCm/GPU enablement
- Intended downstream use: export scored impact tables for MQL5 EA consumption

## Project layout

- `notebooks/` — notebook development
- `src/` — extracted reusable python modules later
- `config/` — local config templates and schema notes
- `data/` — project-local cache/artifacts if needed

## Main notebook

- `notebooks/01_volatility_impact_engine.ipynb`
