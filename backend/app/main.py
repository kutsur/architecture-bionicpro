import logging
import os
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import storage
from .auth import KeycloakAuthenticator
from .database import create_clickhouse_client, fetch_user_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Reports API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_scheme = HTTPBearer(auto_error=False)

keycloak_authenticator = KeycloakAuthenticator(
    well_known_url=os.getenv(
        "KEYCLOAK_WELL_KNOWN_URL",
        "http://keycloak:8080/realms/reports-realm/.well-known/openid-configuration",
    ),
    audience=os.getenv("KEYCLOAK_AUDIENCE") or None,
    issuer_override=os.getenv("KEYCLOAK_ISSUER_OVERRIDE") or None,
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
) -> Dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    return keycloak_authenticator.validate_token(credentials.credentials)


@app.get("/health", tags=["health"])
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/reports", tags=["reports"])
def get_report(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    username = user.get("preferred_username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="preferred_username missing in token",
        )

    key = storage.object_key(username)

    if storage.report_exists(key):
        return {
            "username": username,
            "status": "ready",
            "source": "s3",
            "url": storage.signed_url(key),
        }

    client = create_clickhouse_client()
    try:
        report = fetch_user_report(client, username)
    finally:
        client.close()

    if report is None:
        return {
            "username": username,
            "status": "no_data",
            "message": "Отчёт ещё не готов: данные за запрошенный период не обработаны ETL.",
        }

    storage.put_report(key, report)
    return {
        "username": username,
        "status": "ready",
        "source": "olap",
        "url": storage.signed_url(key),
    }
