import os
from typing import Any, Dict

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", "http://localhost:8090")
S3_BUCKET = os.getenv("S3_BUCKET", "bionicpro-reports")
LINK_TTL_SECONDS = int(os.getenv("REPORT_LINK_TTL", "120"))

_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
_REGION = os.getenv("S3_REGION", "us-east-1")
_CFG = Config(signature_version="s3v4", s3={"addressing_style": "path"})

_internal = boto3.client(
    "s3", endpoint_url=S3_ENDPOINT,
    aws_access_key_id=_ACCESS_KEY, aws_secret_access_key=_SECRET_KEY,
    region_name=_REGION, config=_CFG,
)

_signer = boto3.client(
    "s3", endpoint_url=S3_PUBLIC_ENDPOINT,
    aws_access_key_id=_ACCESS_KEY, aws_secret_access_key=_SECRET_KEY,
    region_name=_REGION, config=_CFG,
)


def object_key(username: str) -> str:
    return f"reports/{username}.json"


def report_exists(key: str) -> bool:
    try:
        _internal.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def put_report(key: str, report: Dict[str, Any]) -> None:
    import json
    body = json.dumps(report, ensure_ascii=False, default=str).encode("utf-8")
    _internal.put_object(
        Bucket=S3_BUCKET, Key=key, Body=body,
        ContentType="application/json",
    )


def signed_url(key: str) -> str:
    return _signer.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=LINK_TTL_SECONDS,
    )
