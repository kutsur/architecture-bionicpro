import logging
from typing import Optional

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

logger = logging.getLogger(__name__)


class KeycloakAuthenticator:
    def __init__(self, well_known_url: str, audience: Optional[str] = None,
                 issuer_override: Optional[str] = None) -> None:
        if not well_known_url:
            raise ValueError("KEYCLOAK_WELL_KNOWN_URL must be configured")
        self.well_known_url = well_known_url.rstrip("/")
        self.audience = audience
        self.issuer_override = issuer_override
        self.issuer: Optional[str] = None
        self.jwks_keys = []
        self.refresh_metadata()

    def refresh_metadata(self) -> None:
        try:
            with httpx.Client(timeout=5) as client:
                metadata = client.get(self.well_known_url).raise_for_status().json()
                jwks = client.get(metadata["jwks_uri"]).raise_for_status().json()
                self.jwks_keys = jwks.get("keys", [])
                self.issuer = self.issuer_override or metadata.get("issuer")
        except Exception as exc:
            logger.exception("Failed to refresh Keycloak metadata")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc

    def _get_signing_key(self, kid: str):
        key = next((k for k in self.jwks_keys if k.get("kid") == kid), None)
        if key is None:
            self.refresh_metadata()
            key = next((k for k in self.jwks_keys if k.get("kid") == kid), None)
        return key

    def validate_token(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid token header") from exc

        signing_key = self._get_signing_key(header.get("kid"))
        if signing_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Unknown signing key")

        options = {"verify_aud": bool(self.audience), "verify_iss": bool(self.issuer)}
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=[header.get("alg", "RS256")],
                audience=self.audience if self.audience else None,
                issuer=self.issuer if self.issuer else None,
                options=options,
            )
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Token validation failed") from exc
        return payload
