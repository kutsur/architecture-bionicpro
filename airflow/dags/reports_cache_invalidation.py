from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task
import boto3

S3_CONNECTION = {
    "endpoint_url": "http://minio:9000",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
    "region_name": "us-east-1",
}
S3_BUCKET = "bionicpro-reports"
S3_REPORTS_PREFIX = "reports/"


@dag(
    dag_id="reports_cache_invalidation",
    description="Periodically drops cached reports in S3 so the CDN serves fresh data from the live CDC mart",
    schedule="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["reports", "cache", "s3"],
)
def reports_cache_invalidation():
    @task()
    def invalidate_cached_reports():
        s3 = boto3.client("s3", **S3_CONNECTION)
        paginator = s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_REPORTS_PREFIX):
            keys.extend({"Key": obj["Key"]} for obj in page.get("Contents", []))
        if keys:
            s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys})

    invalidate_cached_reports()


reports_cache_invalidation()
