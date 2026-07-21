from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from airflow.decorators import dag, task
from clickhouse_driver import Client
import boto3
import psycopg2

S3_CONNECTION = {
    "endpoint_url": "http://minio:9000",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
    "region_name": "us-east-1",
}
S3_BUCKET = "bionicpro-reports"
S3_REPORTS_PREFIX = "reports/"

CRM_CONNECTION = {
    "host": "crm_db",
    "port": 5432,
    "dbname": "crm_db",
    "user": "crm_user",
    "password": "crm_password",
}

CLICKHOUSE_CONNECTION = {
    "host": "olap_db",
    "port": 9000,
    "user": "demo",
    "password": "demo",
    "database": "default",
}


@dag(
    dag_id="crm_to_olap_reporting",
    description="ETL CRM + telemetry -> ClickHouse reporting mart",
    schedule="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["etl", "crm", "clickhouse", "reporting"],
)
def crm_to_olap_reporting():
    @task()
    def fetch_customers() -> List[Tuple]:
        with psycopg2.connect(**CRM_CONNECTION) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT username, full_name, email, birth_date, gender, country
                    FROM customers
                    """
                )
                rows = cursor.fetchall()

        return [
            (
                username or "",
                full_name or "",
                email or "",
                str(birth_date) if birth_date is not None else "",
                gender or "unknown",
                country or "",
            )
            for (username, full_name, email, birth_date, gender, country) in rows
        ]

    @task()
    def load_customers(customers: List[Tuple]):
        client = Client(**CLICKHOUSE_CONNECTION)
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_customers (
                username   String,
                full_name  String,
                email      String,
                birth_date String,
                gender     String,
                country    String
            ) ENGINE = ReplacingMergeTree()
            ORDER BY username
            """
        )
        client.execute("TRUNCATE TABLE crm_customers")
        if customers:
            client.execute(
                "INSERT INTO crm_customers "
                "(username, full_name, email, birth_date, gender, country) VALUES",
                customers,
            )

    @task()
    def build_reporting_mart():
        client = Client(**CLICKHOUSE_CONNECTION)
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS report_user_telemetry (
                username             String,
                full_name            String,
                email                String,
                country              String,
                signals_total        UInt64,
                prosthesis_types     UInt64,
                avg_signal_amplitude Nullable(Decimal(10,4)),
                avg_signal_duration  Nullable(Float64),
                period_start         Nullable(DateTime),
                period_end           Nullable(DateTime)
            ) ENGINE = ReplacingMergeTree()
            ORDER BY username
            """
        )
        client.execute("TRUNCATE TABLE report_user_telemetry")
        client.execute(
            """
            INSERT INTO report_user_telemetry
            SELECT
                c.username                       AS username,
                c.full_name                      AS full_name,
                c.email                          AS email,
                c.country                        AS country,
                count(e.signal_time)             AS signals_total,
                countDistinct(e.prosthesis_type) AS prosthesis_types,
                avgOrNull(e.signal_amplitude)    AS avg_signal_amplitude,
                avgOrNull(e.signal_duration)     AS avg_signal_duration,
                minOrNull(e.signal_time)         AS period_start,
                maxOrNull(e.signal_time)         AS period_end
            FROM crm_customers AS c
            LEFT JOIN emg_sensor_data AS e ON e.username = c.username
            GROUP BY c.username, c.full_name, c.email, c.country
            """
        )

    @task()
    def invalidate_cached_reports():
        s3 = boto3.client("s3", **S3_CONNECTION)
        paginator = s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_REPORTS_PREFIX):
            keys.extend({"Key": obj["Key"]} for obj in page.get("Contents", []))
        if keys:
            s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys})

    customers = fetch_customers()
    loaded = load_customers(customers)
    mart = build_reporting_mart()
    loaded >> mart >> invalidate_cached_reports()


crm_to_olap_reporting()
