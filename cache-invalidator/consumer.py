import json
import os
import time

import boto3
from botocore.client import Config
from kafka import KafkaConsumer

BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "bionicpro_crm.public.customers")
BUCKET = os.getenv("S3_BUCKET", "bionicpro-reports")

s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT", "http://minio:9000"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def connect_consumer():
    while True:
        try:
            return KafkaConsumer(
                TOPIC,
                bootstrap_servers=BROKER,
                group_id="report-cache-invalidator",
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda b: b.decode("utf-8") if b else "",
            )
        except Exception as exc:
            print(f"kafka not ready ({exc}), retrying", flush=True)
            time.sleep(3)


def username_from_event(value: str):
    if not value:
        return None
    event = json.loads(value)
    row = event.get("after") or event.get("before") or {}
    return row.get("username")


def main():
    consumer = connect_consumer()
    print(f"listening {TOPIC} for CDC events", flush=True)
    for message in consumer:
        try:
            username = username_from_event(message.value)
        except Exception:
            continue
        if not username:
            continue
        key = f"reports/{username}.json"
        try:
            s3.delete_object(Bucket=BUCKET, Key=key)
            print(f"invalidated {key}", flush=True)
        except Exception as exc:
            print(f"failed to invalidate {key}: {exc}", flush=True)


if __name__ == "__main__":
    main()
