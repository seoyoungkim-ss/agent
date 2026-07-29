"""PRD 9.2: 파싱이 끝난 정제 데이터만 사내망 HTTPS로 백엔드 /ingest/* API에 전송한다.

원본 파일(엑셀)은 이 과정에서 서버로 전송하지 않는다 — 이미 파싱된 구조화 데이터만
보낸다.
"""

import time
from collections.abc import Iterable

import httpx

from models import ParsedMealLogRow, ParsedMenuRow

_BATCH_SIZE = 500
_MAX_RETRIES = 4
_BACKOFF_SECONDS = (2, 4, 8, 16)


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _post_with_retry(client: httpx.Client, url: str, payload: dict) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0, *_BACKOFF_SECONDS)):
        if delay:
            time.sleep(delay)
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError,) as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                break
    raise RuntimeError(f"백엔드 업로드 실패 ({url}): {last_exc}") from last_exc


def _menu_row_to_dict(row: ParsedMenuRow) -> dict:
    return {
        "plan_date": row.plan_date.isoformat(),
        "meal_type": row.meal_type.value,
        "corner_name": row.corner_name,
        "menu_name": row.menu_name,
        "menu_role": row.menu_role.value,
        "source_row_raw": row.source_row_raw,
    }


def _meal_log_row_to_dict(row: ParsedMealLogRow) -> dict:
    return {
        "eaten_at": row.eaten_at.isoformat(),
        "employee_id": row.employee_id,
        "meal_type": row.meal_type.value,
        "corner_name": row.corner_name,
        "menu_name": row.menu_name,
        "company_name": row.company_name,
        "taste_score": row.taste_score.value if row.taste_score else None,
        "comment": row.comment,
    }


def upload_weekly_menu(
    rows: list[ParsedMenuRow],
    *,
    backend_base_url: str,
    api_token: str,
    timeout: float = 30.0,
    verify_ssl: bool = True,
) -> int:
    return _upload(
        rows, _menu_row_to_dict, f"{backend_base_url}/ingest/weekly-menu", api_token, timeout, verify_ssl
    )


def upload_meal_log(
    rows: list[ParsedMealLogRow],
    *,
    backend_base_url: str,
    api_token: str,
    timeout: float = 30.0,
    verify_ssl: bool = True,
) -> int:
    return _upload(
        rows, _meal_log_row_to_dict, f"{backend_base_url}/ingest/meal-log", api_token, timeout, verify_ssl
    )


def _upload(rows: list, to_dict, url: str, api_token: str, timeout: float, verify_ssl: bool = True) -> int:
    sent = 0
    headers = {"Authorization": f"Bearer {api_token}"}
    with httpx.Client(headers=headers, timeout=timeout, verify=verify_ssl) as client:
        for batch in _chunks(rows, _BATCH_SIZE):
            payload = {"rows": [to_dict(r) for r in batch]}
            _post_with_retry(client, url, payload)
            sent += len(batch)
    return sent
