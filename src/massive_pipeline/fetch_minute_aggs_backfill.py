from __future__ import annotations

import gzip
import io
import json
from datetime import date, timedelta
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

AWS_ACCESS_KEY_ID = "15e42440-7867-4755-99c8-958420b3859d"
AWS_SECRET_ACCESS_KEY = "njD7QQlS6C4hdRLZG7UBC6H2NreHwypW"
ENDPOINT_URL = "https://files.massive.com"
BUCKET = "flatfiles"
RAW_DIR = Path("data/raw/massive/forex/minute_aggs")
START_DATE = date(2023, 1, 1)
END_DATE = date(2026, 3, 31)

TARGET_TICKERS = {
    "C:EUR-JPY",
    "C:GBP-JPY",
    "C:GBP-USD",
    "C:NZD-USD",
}


def iter_dates(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def make_client():
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
            if code == "NoSuchKey":
                manifest.append({"date": d.isoformat(), "key": key, "missing": True})
                print(d.isoformat(), "MISSING")
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
