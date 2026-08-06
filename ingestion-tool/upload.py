"""PRD 9.2: 파싱이 끝난 정제 데이터만 사내망 HTTPS로 백엔드 /ingest/* API에 전송한다.

원본 파일(엑셀)은 이 과정에서 서버로 전송하지 않는다 — 이미 파싱된 구조화 데이터만
보낸다.

**프록시 우회(2026-07 실사용 확인)**: 사내망에는 pip 설치 등을 위해 HTTP_PROXY/
HTTPS_PROXY 환경변수가 걸려있는 경우가 있는데, httpx는 기본(trust_env=True)으로
이 환경변수를 그대로 읽어 backend_base_url(사내 전용 서버)행 요청까지 그 프록시로
보내려다 프록시가 403을 돌려주는 문제가 있었다(llm_client.py에서 먼저 발견된 것과
동일한 원인). 아래 클라이언트도 trust_env=False로 이 환경변수를 무시하고 직접
접속한다.
"""

import time
from collections.abc import Iterable
from typing import NamedTuple

import httpx

from models import ParsedMealLogRow, ParsedMenuRow

_BATCH_SIZE = 500
_MAX_RETRIES = 4
_BACKOFF_SECONDS = (2, 4, 8, 16)


class UploadSummary(NamedTuple):
    """전송 결과. `sent`만 쓰던 호출부가 있어 첫 필드를 유지한다.

    skipped_*는 백엔드가 알려주는 값이다 — 재업로드했는데 화면이 그대로일 때
    "왜 그대로인지"(관리자 수정을 보존했다)를 운영자에게 설명하기 위한 것.
    """

    sent: int
    skipped_manual: int = 0
    skipped_duplicate: int = 0


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _menu_slot_key(row: ParsedMenuRow) -> tuple:
    """식단표의 "슬롯" — 백엔드가 replace_existing에서 통째로 지우는 단위."""
    return (row.plan_date, row.corner_name, row.meal_type)


def _slot_aware_chunks(rows: list[ParsedMenuRow], size: int) -> Iterable[list[ParsedMenuRow]]:
    """같은 슬롯의 행이 **서로 다른 요청으로 갈라지지 않게** 잘라 준다.

    ⚠️ 이게 없으면 `replace_existing=True`에서 데이터가 사라진다. 백엔드는
    **요청마다** payload에 등장하는 (plan_date, corner, meal_type) 슬롯을 지우고
    넣는다(app/api/ingest.py). 한 슬롯이 청크 경계에 걸치면 **두 번째 요청이
    첫 번째 요청으로 넣은 행을 지운다.**

    주 1개는 보통 500행 미만이라 지금은 안 터지지만, 조식·석식까지 파싱을 켜면
    넘는다 — 그때 조용히 부찬 몇 개가 사라지는 형태로 나타난다.

    슬롯 하나가 혼자 size를 넘으면 그 슬롯만 단독 청크로 보낸다(쪼개는 것보다
    큰 요청 하나가 낫다).
    """
    groups: dict[tuple, list[ParsedMenuRow]] = {}
    for row in rows:
        groups.setdefault(_menu_slot_key(row), []).append(row)

    current: list[ParsedMenuRow] = []
    for group in groups.values():  # dict는 삽입 순서를 유지한다 — 원본 순서 보존
        if current and len(current) + len(group) > size:
            yield current
            current = []
        current.extend(group)
    if current:
        yield current


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
    replace_existing: bool = False,
) -> UploadSummary:
    """replace_existing=True면 같은 슬롯의 기존 행을 지우고 넣는다(멱등 재적재).

    기본값이 False라 기존 호출부 동작은 안 바뀐다. True일 때는 슬롯이 요청
    경계로 갈라지지 않게 청킹 방식도 함께 바뀐다(`_slot_aware_chunks` 참고).
    """
    return _upload(
        rows,
        _menu_row_to_dict,
        f"{backend_base_url}/ingest/weekly-menu",
        api_token,
        timeout,
        verify_ssl,
        extra_payload={"replace_existing": True} if replace_existing else None,
        chunker=_slot_aware_chunks if replace_existing else None,
    )


def upload_meal_log(
    rows: list[ParsedMealLogRow],
    *,
    backend_base_url: str,
    api_token: str,
    timeout: float = 30.0,
    verify_ssl: bool = True,
) -> UploadSummary:
    return _upload(
        rows, _meal_log_row_to_dict, f"{backend_base_url}/ingest/meal-log", api_token, timeout, verify_ssl
    )


def _upload(
    rows: list,
    to_dict,
    url: str,
    api_token: str,
    timeout: float,
    verify_ssl: bool = True,
    *,
    extra_payload: dict | None = None,
    chunker=None,
) -> UploadSummary:
    sent = 0
    skipped_manual = 0
    skipped_duplicate = 0
    headers = {"Authorization": f"Bearer {api_token}"}
    split = chunker or _chunks
    with httpx.Client(headers=headers, timeout=timeout, verify=verify_ssl, trust_env=False) as client:
        for batch in split(rows, _BATCH_SIZE):
            payload = {"rows": [to_dict(r) for r in batch], **(extra_payload or {})}
            resp = _post_with_retry(client, url, payload)
            sent += len(batch)
            # 백엔드가 안 알려주는 구버전이거나 테스트가 갈아끼운 경우엔 조용히 0.
            body = _response_counts(resp)
            skipped_manual += body.get("skipped_manual", 0)
            skipped_duplicate += body.get("skipped_duplicate", 0)
    return UploadSummary(sent, skipped_manual, skipped_duplicate)


def _response_counts(resp) -> dict:
    if resp is None:
        return {}
    try:
        body = resp.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}
