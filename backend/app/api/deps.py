from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings


def require_ingest_token(authorization: str | None = Header(default=None)) -> None:
    """PRD 9.2: ingestion-tool이 /ingest/* 호출 시 보내는 단순 Bearer 토큰 검증."""
    settings = get_settings()
    expected = f"Bearer {settings.ingest_api_token}"
    if not authorization or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingest token")
