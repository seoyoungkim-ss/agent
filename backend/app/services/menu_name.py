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
import unicodedata

from app.services.corner_aliases import ALL_CORNER_NAMES

_PAREN_GROUP_PATTERN = re.compile(r"\s*\(([^()]*)\)")
_ORIGIN_SEPARATOR = re.compile(r"[:\-–—/]|\s+")
_ORIGIN_EXPLICIT_TOKENS = {"국내산", "국산", "외국산", "수입산", "원양산"}
# 원산지 토큰 길이 상한. 6자였는데 `노르웨이자연산`(7자)을 못 잡아 메뉴가 갈라졌다
# (2026-08 "연어파피요트가 매칭 안 됨" 신고). 8자면 `뉴질랜드산`류까지 덮는다.
_ORIGIN_TOKEN_MAX_LEN = 8

# POS 표시명 앞에 붙는 판매 형태 표기 — 메뉴 이름이 아니다.
# `strip_origin_annotation`은 `$` 앵커라 뒤쪽만 떼므로 앞쪽은 여기서 처리한다.
_LEADING_ANNOTATIONS = ("(포장)", "(테이크아웃)", "(take out)", "(TO)")


def looks_like_origin_token(token: str) -> bool:
    """"국내산", "호주산", "노르웨이자연산"처럼 원산지 이름으로 보이는 토큰인가.

    "산"으로 끝나는 2~8자만 인정한다 — "매운맛"·"얼큰한맛"·"태양초" 같은 메뉴
    설명이 원산지로 오인되면 멀쩡한 이름이 잘려 나간다.
    """
    t = token.strip()
    if not t:
        return False
    if t in _ORIGIN_EXPLICIT_TOKENS:
        return True
    return 2 <= len(t) <= _ORIGIN_TOKEN_MAX_LEN and t.endswith("산")


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


# 조리법 어미 — 이걸로 끝나는 토큰은 재료가 아니라 **요리 이름**이다.
# `(오징어볶음-매운맛)`처럼 괄호 안에 메뉴명이 통째로 들어온 경우를 재료 주석과
# 구분하는 단서. 재료 주석의 앞 토큰은 `햄`·`돈육`·`계육`처럼 재료명이다.
# ⚠️ 휴리스틱이다 — 여기 없는 조리법으로 끝나는 메뉴가 괄호 안에 통째로 들어오면
# 주석으로 오인해 지운다. 실제 파일을 보며 계속 보강해야 한다.
_DISH_SUFFIXES: tuple[str, ...] = (
    "볶음", "구이", "찜", "탕", "조림", "무침", "튀김", "전", "국", "찌개", "말이",
    "쌈", "샐러드", "steak", "스테이크", "까스", "카츠", "덮밥", "밥", "면", "국수",
    "만두", "죽", "스프", "수프", "피자", "파스타", "그라탕", "리조또",
)


def _looks_like_dish_name(token: str) -> bool:
    t = token.strip()
    return bool(t) and t.endswith(_DISH_SUFFIXES)


def is_ingredient_pair(entry: str) -> bool:
    """`햄-계육` / `돈육:국내산`처럼 **재료 짝**으로 적힌 항목인가.

    담당자 요청(2026-08): `(햄-계육, 돈육:국내산)`처럼 원산지가 아닌 재료 구성이
    섞여 있어도 통째로 주석으로 봐야 한다.
    """
    parts = [p for p in _ORIGIN_SEPARATOR.split(entry.strip()) if p]
    if len(parts) < 2:
        return False
    return not _looks_like_dish_name(parts[0])


def _entries_are_removable(entries: list[str], *, allow_bare: bool) -> bool:
    """괄호 안 항목들이 전부 원산지이거나 전부 재료 짝이면 지워도 된다.

    `is_origin_annotation_text`(셀 전체 판정)와 `strip_origin_annotation`
    (이름 뒤 주석 제거)이 각자 규칙을 따로 들고 있다가 한쪽만 재료-짝 폴백을
    받고 한쪽은 못 받는 사고가 났다(2026-08, "햄마늘종볶음(햄-계육, 돈육:
    국내산)"이 안 떨어짐). 하나로 합쳐 두 함수가 항상 같은 판정을 하게 한다.

    괄호 안이 항목 하나뿐이고 그 값이 **알려진 코너 이름/별칭과 완전히 일치**
    하면 그것도 지운다(2026-08, "진짬뽕라면(스냅스낵)"/"진짬뽕라면(스냅스넥)"이
    코너명 표기 차이로 다른 메뉴처럼 갈라지던 문제) — 원산지 휴리스틱과는
    별개의 화이트리스트 판정이라 "김치찌개(얼큰한맛)"처럼 실제로 다른 메뉴를
    구분하는 임의의 괄호 설명에는 영향을 주지 않는다.
    """
    if not entries:
        return False
    if all(is_origin_entry(e, allow_bare=allow_bare) for e in entries):
        return True
    if allow_bare and all(is_ingredient_pair(e) for e in entries):
        return True
    return len(entries) == 1 and entries[0].strip() in ALL_CORNER_NAMES


def is_origin_annotation_text(text: str) -> bool:
    """이 문자열이 **통째로** 재료/원산지 표기인가 — 버려야 하는 줄인지.

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
    return _entries_are_removable(entries, allow_bare=allow_bare)


def strip_origin_annotation(menu_name: str) -> str:
    """메뉴명 안에 있는 "(재료:원산지)" 주석을 제거해 메뉴명만 남긴다.

    ⚠️ 문자열 끝에 있는 것만 지우지 않는다. 예전엔 끝에 고정된 패턴으로
    돌면서 끝에서부터 벗겨냈는데, "명란크림파스타(명란:미국산)&베이컨포테이토
    피자"처럼 괄호 뒤에 "&메뉴명"이 더 붙는 경우 괄호가 끝이 아니게 돼
    아예 안 지워졌다(2026-08 실사용 신고). 이제 문자열 안의 모든 괄호
    그룹을 훑어 원산지/재료 짝으로 판정되는 것만 지운다.

    괄호 안 항목이 원산지처럼 보이지 않으면 지우지 않는다 —
    "(오징어볶음-매운맛)"처럼 메뉴 설명이 붙은 경우를 지우면 안 된다.
    """

    def _replace(match: re.Match) -> str:
        entries = [e for e in match.group(1).split(",") if e.strip()]
        return "" if _entries_are_removable(entries, allow_bare=True) else match.group(0)

    result = _PAREN_GROUP_PATTERN.sub(_replace, menu_name)
    return re.sub(r"\s{2,}", " ", result).strip()


# ---------------------------------------------------------------------------
# 매칭 키 — 표시명과 분리한다 (2026-08)
# ---------------------------------------------------------------------------
# 신고: "연어파피요트 취식현황에도 있고 주간식단표에 있는데 매칭이 안되고있음".
#
# 원인은 메뉴 join이 사실상 **정확 문자열 비교**라는 것이었다. `menu_master.
# menu_name`이 바이트 단위 unique라 아래가 전부 별개 행이 된다:
#
#   연어파피요트 / 연어 파피요트 / 연어파피요트（연어:노르웨이산） / (포장)연어파피요트
#
# ⚠️ **표시명을 정규화해 저장하면 안 된다.** 담당자가 화면에서 원문을 확인할 수
# 없게 되고(엑셀 셀과 대조 불가), 감사 추적도 끊긴다. 그래서 원문은 그대로 두고
# **조회용 키만 따로** 만든다(`menu_master.match_key`).


def match_key(menu_name: str) -> str:
    """같은 메뉴로 볼 이름들을 하나로 접는 **조회 전용** 키.

    표시용이 아니다 — 공백까지 지우므로 사람이 읽으라고 만든 값이 아니다.

    1. NFKC 정규화 — 전각 괄호 `（）`·전각 `＆`·전각 공백을 반각으로
    2. 앞에 붙은 판매 형태 주석 제거 — `(포장)연어파피요트`
    3. 뒤에 붙은 원산지 주석 제거 — `연어파피요트(연어:노르웨이산)`
    4. 공백 전부 제거 — `연어 파피요트` == `연어파피요트`
    5. 소문자화 — `Take Out` == `take out`
    """
    text = unicodedata.normalize("NFKC", menu_name or "").strip()

    changed = True
    while changed:
        changed = False
        for prefix in _LEADING_ANNOTATIONS:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix) :].strip()
                changed = True
        stripped = strip_origin_annotation(text)
        if stripped != text:
            text, changed = stripped, True

    return "".join(text.split()).lower()


def pair_likely_same_menu(
    plan_only: list[str], log_only: list[str]
) -> list[dict[str, str]]:
    """양쪽 목록에서 **정규화하면 같아지는** 이름 짝을 찾는다.

    매칭 진단은 `menu_id` 정수 비교라, 표기만 다른 같은 메뉴가 `plan_only`와
    `log_only`에 **동시에** 뜬다(2026-08 "연어파피요트" 신고). 담당자가 두 목록을
    눈으로 대조해야 했던 걸 기계가 짚어준다.

    순수 함수 — DB를 모른다(레포 관례).
    """
    log_by_key = {match_key(name): name for name in log_only}
    return [
        {"plan_name": name, "log_name": log_by_key[match_key(name)]}
        for name in plan_only
        if match_key(name) in log_by_key
    ]
