from __future__ import annotations

import gzip
import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_env import load_project_env

load_project_env()

AWS_ACCESS_KEY_ID = os.environ.get("MASSIVE_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("MASSIVE_SECRET_ACCESS_KEY", "")
ENDPOINT_URL = os.environ.get("MASSIVE_S3_ENDPOINT", "https://files.massive.com")
BUCKET = os.environ.get("MASSIVE_BUCKET", "flatfiles")
RAW_DIR = Path("data/raw/massive/forex/minute_aggs")
START_DATE = date(2023, 1, 1)
END_DATE = datetime.now(timezone.utc).date()

TARGET_TICKERS = {
    "C:EUR-USD",
    "C:USD-JPY",
    "C:GBP-USD",
    "C:USD-CHF",
    "C:AUD-USD",
    "C:USD-CAD",
    "C:NZD-USD",
    "C:EUR-GBP",
    "C:EUR-JPY",
    "C:EUR-CHF",
    "C:EUR-AUD",
    "C:EUR-CAD",
    "C:EUR-NZD",
    "C:GBP-JPY",
    "C:GBP-CHF",
    "C:GBP-AUD",
    "C:GBP-CAD",
    "C:GBP-NZD",
    "C:AUD-JPY",
    "C:AUD-CHF",
    "C:AUD-CAD",
    "C:AUD-NZD",
    "C:CAD-JPY",
    "C:CAD-CHF",
    "C:CHF-JPY",
    "C:NZD-JPY",
    "C:NZD-CHF",
    "C:NZD-CAD",
}


def iter_dates(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def make_client():
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        raise RuntimeError("Missing Massive S3 credentials. Set MASSIVE_ACCESS_KEY_ID and MASSIVE_SECRET_ACCESS_KEY.")
    session = boto3.session.Session()
    return session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=ENDPOINT_URL,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def key_for_day(d: date) -> str:
    return f"global_forex/minute_aggs_v1/{d.year:04d}/{d.month:02d}/{d.isoformat()}.csv.gz"


def filter_csv_bytes(raw_gz: bytes) -> bytes:
    src = gzip.GzipFile(fileobj=io.BytesIO(raw_gz), mode="rb")
    out_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=out_buf, mode="wb") as dst:
        header = src.readline()
        dst.write(header)
        for line in src:
            ticker = line.split(b",", 1)[0].decode("utf-8", "replace")
            if ticker in TARGET_TICKERS:
                dst.write(line)
    return out_buf.getvalue()


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    s3 = make_client()
    manifest = []

    for d in iter_dates(START_DATE, END_DATE):
        out_dir = RAW_DIR / f"{d.year:04d}" / f"{d.month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{d.isoformat()}.csv.gz"
        if out_path.exists():
            manifest.append({"date": d.isoformat(), "out": str(out_path), "skipped_existing": True})
            continue

        key = key_for_day(d)
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code == "NoSuchKey" or status == 404:
                manifest.append({"date": d.isoformat(), "key": key, "missing": True})
                print(d.isoformat(), "MISSING")
                continue
            if status == 403:
                manifest.append({"date": d.isoformat(), "key": key, "forbidden": True})
                print(d.isoformat(), "FORBIDDEN")
                continue
            raise

        raw_gz = obj["Body"].read()
        filtered_gz = filter_csv_bytes(raw_gz)
        out_path.write_bytes(filtered_gz)
        manifest.append({"date": d.isoformat(), "key": key, "out": str(out_path), "missing": False})
        print(d.isoformat(), len(filtered_gz))

    (RAW_DIR / "backfill_manifest_2023_2026q1.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
