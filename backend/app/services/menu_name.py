"""메뉴명 정규화 — 원산지 주석 제거 (2026-08 재작성).

식단표 셀에는 `우삼겹구이(우육:호주산)` `(계육-국산)` `*돈육:국내산`처럼 재료의
원산지가 함께 적혀 온다. 취식기록·맛평가에는 원산지가 없어 이 표기가 남으면
같은 메뉴가 서로 다른 `MenuMaster` row로 갈라진다.

**⚠️ 이 판정은 `ingestion-tool/parsing/weekly_menu_parser.py`와 같은 규칙이다.**
두 패키지가 분리돼 코드를 공유할 수 없어 복제하고 있다 — 한쪽만 고치면 조용히
어긋난다. 실제로 2026-08까지 "콜론만 인정하는" 낡은 정규식이 양쪽에 복제돼 있어
`(계육-국산)` 같은 하이픈 표기를 둘 다 놓쳤다. 그래서 양쪽에 같은 케이스
테스트를 두어 어긋나면 깨지게 했다(`test_menu_name.py` ↔
`ingestion-tool/tests/test_weekly_menu_parser.py`).

백엔드 안에서는 이 모듈이 유일한 출처다 — `master_data`와 `food_vector_tagging`이
서로를 임포트하고 있어(순환) 어느 한쪽에 두면 안 된다.
"""

import re

_TRAILING_PAREN = re.compile(r"\s*\(([^()]*)\)\s*$")
_ORIGIN_SEPARATOR = re.compile(r"[:\-–—/]|\s+")
_ORIGIN_EXPLICIT_TOKENS = {"국내산", "국산", "외국산", "수입산", "원양산"}


def looks_like_origin_token(token: str) -> bool:
    """"국내산", "호주산", "브라질산"처럼 원산지 이름으로 보이는 토큰인가.

    "산"으로 끝나는 2~6자만 인정한다 — "매운맛"·"얼큰한맛"·"태양초" 같은 메뉴
    설명이 원산지로 오인되면 멀쩡한 이름이 잘려 나간다.
    """
    t = token.strip()
    if not t:
        return False
    if t in _ORIGIN_EXPLICIT_TOKENS:
        return True
    return 2 <= len(t) <= 6 and t.endswith("산")


def is_origin_entry(entry: str, *, allow_bare: bool = False) -> bool:
    """"우육:호주산" / "계육-국산" / "오징어 중국산" 한 건인지.

    allow_bare=True면 `(중국산)`처럼 재료 없이 원산지만 있는 형태도 인정한다 —
    괄호 밖에 메뉴명이 따로 있는 상황이라 오인 위험이 낮다.
    """
    parts = [p for p in _ORIGIN_SEPARATOR.split(entry.strip()) if p]
    if not parts:
        return False
    if len(parts) >= 2:
        return looks_like_origin_token(parts[-1])
    return allow_bare and looks_like_origin_token(parts[0])


def strip_origin_annotation(menu_name: str) -> str:
    """메뉴명 끝의 원산지 주석을 뗀다. 괄호 안이 전부 원산지일 때만 제거한다."""
    while True:
        match = _TRAILING_PAREN.search(menu_name)
        if match is None:
            return menu_name.strip()
        entries = [e for e in match.group(1).split(",") if e.strip()]
        if not entries or not all(is_origin_entry(e, allow_bare=True) for e in entries):
            return menu_name.strip()
        menu_name = menu_name[: match.start()].strip()


def is_origin_annotation_text(text: str) -> bool:
    """이 문자열이 **통째로** 원산지 표기인가 — 메뉴가 아니라 버려야 하는 줄인지.

    `우삼겹구이(우육:호주산)`처럼 메뉴명이 앞에 붙어 있으면 False다 — 통째로
    버리면 메뉴가 사라지므로 그건 `strip_origin_annotation`이 담당한다.
    """
    t = text.strip().lstrip("*※ \t").strip()
    if not t:
        return False
    if t.startswith("(") and t.endswith(")"):
        inner, allow_bare = t[1:-1], True
    elif "(" not in t and ")" not in t:
        inner, allow_bare = t, False  # 괄호 없는 `*돈육:국내산` 형태
    else:
        return False  # 메뉴명 + 주석 혼합
    entries = [e for e in inner.split(",") if e.strip()]
    return bool(entries) and all(is_origin_entry(e, allow_bare=allow_bare) for e in entries)
