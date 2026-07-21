import json
import os
from typing import Any, Dict, Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.getenv("S3_BUCKET", "bionicpro-reports")
CDN_BASE_URL = os.getenv("CDN_BASE_URL", "http://localhost:8090/reports-cache")

_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
    region_name=os.getenv("S3_REGION", "us-east-1"),
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def object_key(username: str) -> str:
    return f"reports/{username}.json"


def report_exists(key: str) -> bool:
    try:
        _client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def put_report(key: str, report: Dict[str, Any]) -> None:
    body = json.dumps(report, ensure_ascii=False, default=str).encode("utf-8")
    _client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )


def cdn_url(key: str) -> str:
    return f"{CDN_BASE_URL}/{key}"
