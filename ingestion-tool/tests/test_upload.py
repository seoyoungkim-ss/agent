"""업로드 페이로드 — 특히 `replace_existing`과 청크 분할의 상호작용.

여기 테스트가 지키려는 건 성능이 아니라 **데이터 손실**이다. 백엔드는 요청마다
payload에 등장하는 (plan_date, corner, meal_type) 슬롯을 지우고 넣으므로
(app/api/ingest.py), 한 슬롯이 두 요청으로 갈라지면 뒤 요청이 앞 요청의 삽입분을
지운다. 실제 파일을 안 띄우고도 잡을 수 있는 종류의 버그라 여기서 고정한다.
"""

import datetime as dt

import pytest

import upload
from models import MealType, MenuRole, ParsedMenuRow


def _row(day: int, corner: str = "한식", name: str = "메뉴", role: MenuRole = MenuRole.SIDE):
    return ParsedMenuRow(
        plan_date=dt.date(2026, 7, day),
        meal_type=MealType.LUNCH,
        corner_name=corner,
        menu_name=name,
        menu_role=role,
        source_row_raw=None,
    )


@pytest.fixture
def captured(monkeypatch):
    """실제 HTTP 없이 전송된 페이로드만 모은다."""
    payloads = []
    monkeypatch.setattr(
        upload, "_post_with_retry", lambda client, url, payload: payloads.append(payload)
    )
    return payloads


def _upload(rows, **kwargs):
    return upload.upload_weekly_menu(
        rows, backend_base_url="https://x/api", api_token="t", **kwargs
    )


# ---------------------------------------------------------------------------
# replace_existing 전달
# ---------------------------------------------------------------------------


def test_replace_existing_is_not_sent_by_default(captured):
    """기본값은 기존 동작 그대로 — 안 보내면 백엔드가 False로 둔다."""
    _upload([_row(6)])
    assert "replace_existing" not in captured[0]


def test_replace_existing_is_sent_when_requested(captured):
    _upload([_row(6)], replace_existing=True)
    assert captured[0]["replace_existing"] is True


def test_every_chunk_carries_replace_existing(captured, monkeypatch):
    """여러 요청으로 갈릴 때 일부만 교체 모드면 나머지가 덧붙어 중복이 남는다."""
    monkeypatch.setattr(upload, "_BATCH_SIZE", 2)
    rows = [_row(day) for day in range(6, 12)]  # 슬롯 6개 → 요청 3개
    _upload(rows, replace_existing=True)
    assert len(captured) > 1
    assert all(p["replace_existing"] is True for p in captured)


# ---------------------------------------------------------------------------
# 슬롯이 요청 경계로 갈라지지 않는다 (핵심)
# ---------------------------------------------------------------------------


def test_slot_is_never_split_across_requests(captured, monkeypatch):
    """한 슬롯의 행이 두 요청에 걸치면 뒤 요청이 앞 요청 삽입분을 지운다.

    슬롯 하나에 3행씩인데 배치 크기를 2로 줄여, 순진하게 자르면 반드시 갈라지는
    상황을 만든다.
    """
    monkeypatch.setattr(upload, "_BATCH_SIZE", 2)
    rows = [_row(day, name=f"메뉴{i}") for day in (6, 7) for i in range(3)]
    _upload(rows, replace_existing=True)

    seen: set[str] = set()
    for payload in captured:
        dates = {r["plan_date"] for r in payload["rows"]}
        # 앞선 요청에 이미 나온 날짜가 다시 나오면 그 슬롯이 갈라진 것이다.
        assert not (dates & seen), f"슬롯이 갈라졌습니다: {dates & seen}"
        seen |= dates


def test_oversized_single_slot_goes_out_alone(captured, monkeypatch):
    """슬롯 하나가 배치 크기를 넘어도 쪼개지 않는다 — 쪼개면 자기가 자기를 지운다."""
    monkeypatch.setattr(upload, "_BATCH_SIZE", 2)
    rows = [_row(6, name=f"메뉴{i}") for i in range(5)]
    _upload(rows, replace_existing=True)
    assert len(captured) == 1
    assert len(captured[0]["rows"]) == 5


def test_all_rows_are_still_sent_exactly_once(captured, monkeypatch):
    """슬롯 단위로 묶느라 행이 새거나 중복되면 안 된다."""
    monkeypatch.setattr(upload, "_BATCH_SIZE", 2)
    rows = [_row(day, name=f"메뉴{day}-{i}") for day in (6, 7, 8) for i in range(2)]
    result = _upload(rows, replace_existing=True)

    names = [r["menu_name"] for p in captured for r in p["rows"]]
    assert result.sent == len(rows)
    assert sorted(names) == sorted(r.menu_name for r in rows)


def test_different_corners_on_the_same_day_are_separate_slots(captured, monkeypatch):
    """슬롯 키는 날짜만이 아니라 (날짜, 코너, 식사구분)이다."""
    monkeypatch.setattr(upload, "_BATCH_SIZE", 2)
    rows = [_row(6, corner="한식"), _row(6, corner="한식"), _row(6, corner="양식")]
    _upload(rows, replace_existing=True)
    assert len(captured) == 2
    assert {r["corner_name"] for r in captured[0]["rows"]} == {"한식"}
    assert {r["corner_name"] for r in captured[1]["rows"]} == {"양식"}


def test_row_order_within_a_slot_is_preserved(captured):
    """메인이 먼저 오는 순서가 뒤집히면 감사 시 원문 대조가 어려워진다."""
    rows = [_row(6, name="제육볶음", role=MenuRole.MAIN), _row(6, name="김치")]
    _upload(rows, replace_existing=True)
    assert [r["menu_name"] for r in captured[0]["rows"]] == ["제육볶음", "김치"]
