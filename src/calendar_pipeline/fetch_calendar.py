from __future__ import annotations

import argparse
import calendar
import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable
import http.client

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_env import load_project_env

load_project_env()

API_HOST = "ultimate-economic-calendar.p.rapidapi.com"
DEFAULT_COUNTRIES = ["US", "GB", "JP", "NZ", "DE"]


@dataclass(frozen=True)
class MonthWindow:
    year: int
    month: int

    @property
    def start_date(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end_date(self) -> date:
        last_day = calendar.monthrange(self.year, self.month)[1]
        return date(self.year, self.month, last_day)

    @property
    def slug(self) -> str:
        return f"{self.year}-{self.month:02d}"


def iter_months(start_year: int, end_year: int, end_month_by_year: dict[int, int]) -> Iterable[MonthWindow]:
    for year in range(start_year, end_year + 1):
        max_month = end_month_by_year.get(year, 12)
        for month in range(1, max_month + 1):
            yield MonthWindow(year, month)


def build_path(window: MonthWindow, countries: list[str]) -> str:
    countries_q = ",".join(countries)
    return (
        f"/economic-events/tradingview?from={window.start_date.isoformat()}"
        f"&to={window.end_date.isoformat()}&countries={countries_q}"
    )


def fetch_window(api_key: str, path: str) -> tuple[int, dict[str, str], str]:
    conn = http.client.HTTPSConnection(API_HOST, timeout=60)
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json",
    }
    conn.request("GET", path, headers=headers)
    res = conn.getresponse()
    body = res.read().decode("utf-8", "replace")
    return res.status, {k: v for k, v in res.getheaders()}, body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("RAPIDAPI_KEY", ""))
    parser.add_argument("--out-dir", default="data/raw/economic_calendar")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--countries", default=",".join(DEFAULT_COUNTRIES))
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Pass --api-key or set RAPIDAPI_KEY.")

    countries = [c.strip() for c in args.countries.split(",") if c.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    end_month_by_year = {2023: 12, 2024: 12, 2025: 12, 2026: 6}
    windows = list(iter_months(2023, 2026, end_month_by_year))

    manifest: list[dict[str, object]] = []
    for window in windows:
        year_dir = out_dir / str(window.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        out_file = year_dir / f"{window.slug}.json"
        path = build_path(window, countries)
        status, headers, body = fetch_window(args.api_key, path)
        record = {
            "window": window.slug,
            "request_path": path,
            "status": status,
            "remaining": headers.get("X-RateLimit-Requests-Remaining"),
            "result_count": None,
        }
        payload = {
            "meta": record,
            "headers": headers,
            "body": None,
        }
        try:
            data = json.loads(body)
            payload["body"] = data
            if isinstance(data, dict) and isinstance(data.get("result"), list):
                record["result_count"] = len(data["result"])
        except json.JSONDecodeError:
            payload["body"] = body
        out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        manifest.append(record)
        print(json.dumps(record))
        if status != 200:
            raise SystemExit(f"Stopping on HTTP {status} for {window.slug}")
        time.sleep(args.sleep_seconds)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
