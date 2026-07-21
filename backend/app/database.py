import logging
import os
from typing import Any, Dict, Optional

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

REPORT_COLUMNS = [
    "username",
    "full_name",
    "email",
    "country",
    "signals_total",
    "prosthesis_types",
    "avg_signal_amplitude",
    "avg_signal_duration",
    "period_start",
    "period_end",
]


def create_clickhouse_client() -> Client:
    try:
        return clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            database=os.getenv("CLICKHOUSE_DATABASE", "default"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to analytics store",
        ) from exc


def fetch_user_report(client: Client, username: str) -> Optional[Dict[str, Any]]:
    try:
        result = client.query(
            f"SELECT {', '.join(REPORT_COLUMNS)} "
            "FROM report_user_telemetry "
            "WHERE username = {username:String} "
            "LIMIT 1",
            parameters={"username": username},
        )
    except Exception as exc:
        logger.exception("ClickHouse query failed while building report")
        raise HTTPException(status_code=500, detail="Failed to build report") from exc

    if not result.result_rows:
        return None
    return dict(zip(REPORT_COLUMNS, result.result_rows[0]))
