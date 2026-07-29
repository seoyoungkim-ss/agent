"""운영자 PC에 배포되는 실행 파일(.exe) 옆에 두는 config.json을 읽는다.

config.example.json을 config.json으로 복사해 실제 값을 채운다 (config.json은
.gitignore에 등록되어 저장소에 커밋되지 않는다 — PRD 9.5 환경변수 관리 원칙과 동일).
환경변수(INGEST_BACKEND_URL / INGEST_API_TOKEN)가 있으면 그것을 우선한다.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass(frozen=True)
class ToolConfig:
    backend_base_url: str
    api_token: str
    # 사번↔Knox ID 매핑 CSV 경로 (parsing/employee_mapping.py). 선택 항목 — 없으면
    # A사(사번==Knox ID) 외 인원은 맛평가 매칭이 안 되고 "미평가"로 남는다.
    employee_mapping_path: str | None = None
    # 기본 True(항상 검증). 사내 SSL 검사(프록시가 자체 인증서로 가로채는 경우 등)
    # 때문에 검증이 막힐 때만 False로 — 그 경우에도 사내망 안에서만 통신하는
    # backend_base_url(사내 서버)에 한해 쓰는 걸 전제로 한다. 가능하면 이 값을 끄는
    # 대신 사내 루트 인증서를 OS/Python 신뢰 저장소에 설치하는 게 더 안전하다.
    verify_ssl: bool = True


def _parse_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() not in ("false", "0", "no")


def load_config() -> ToolConfig:
    file_values: dict = {}
    if _CONFIG_PATH.exists():
        file_values = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))

    backend_base_url = os.environ.get("INGEST_BACKEND_URL") or file_values.get("backend_base_url")
    api_token = os.environ.get("INGEST_API_TOKEN") or file_values.get("api_token")
    employee_mapping_path = os.environ.get("INGEST_EMPLOYEE_MAPPING_PATH") or file_values.get(
        "employee_mapping_path"
    )
    verify_ssl = _parse_bool(
        os.environ.get("INGEST_VERIFY_SSL") if "INGEST_VERIFY_SSL" in os.environ else file_values.get("verify_ssl"),
        default=True,
    )

    if not backend_base_url or not api_token:
        raise RuntimeError(
            "backend_base_url / api_token이 설정되지 않았습니다. "
            "config.example.json을 config.json으로 복사해 값을 채우거나 "
            "INGEST_BACKEND_URL / INGEST_API_TOKEN 환경변수를 설정하세요."
        )
    return ToolConfig(
        backend_base_url=backend_base_url.rstrip("/"),
        api_token=api_token,
        employee_mapping_path=employee_mapping_path,
        verify_ssl=verify_ssl,
    )
