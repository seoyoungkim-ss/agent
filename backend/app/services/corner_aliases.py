"""코너 별칭 — 같은 코너가 엑셀마다 다르게 표기돼 들어오는 경우를 위한 상수.

`master_data.py`(코너명 정규화)와 `menu_name.py`(메뉴명 끝에 붙은 코너 별칭
접미어 제거, 2026-08) 양쪽에서 쓴다. 이 상수만 담은 의존성 없는 모듈로 분리한
이유는 `menu_name.py`가 "백엔드 안의 유일한 정규화 출처"라 코너 지식을 직접
가지면 안 되는데(자기 docstring에 명시된 순환 임포트 우려 — master_data와
food_vector_tagging이 서로를 이미 임포트하고 있음), 두 모듈이 같은 별칭
데이터를 공유는 해야 하기 때문이다.
"""

TAKE_OUT_CORNER_NAME = "Take Out"
# 취식기록 "코너" 컬럼 원문 — 같은 Take Out을 R/M/L 단말기 + "선택형 Take out"으로
# 나눠 찍는다(2026-07 실사용 확인 — "선택형 Take out"은 소문자 o). 전부 하나의
# 코너로 합친다.
TAKE_OUT_ALIASES = {"Take Out R", "Take Out M", "Take Out L", "선택형 Take out"}

SNAP_SNACK_CORNER_NAME = "스냅스낵"
# 엑셀마다 "스냅스낵"/"스냅스넥"으로 표기가 갈려 같은 코너가 둘로 나뉘어
# 집계되던 문제(2026-08 실사용 신고) — 하나로 합친다.
SNAP_SNACK_ALIASES = {"스냅스낵", "스냅스넥"}

# §76(2026-08): 담당자 요청으로 메인메뉴 날씨유형·계절 랭킹 집계에서 제외하는
# 코너 — 별칭이 따로 없어(항상 "미캠회관(전골)" 한 표기로만 들어옴) 알리아스
# 그룹 없이 이름만 둔다.
MICAM_HALL_CORNER_NAME = "미캠회관(전골)"

# §77(2026-08): 배식 성격상 식수가 원래 적어도 정상인 코너들(스낵/다이어트식/
# 전골 특성) — 주간 식단표 규칙검증의 "최근 식수 200식 이하 메뉴는 재편성
# 금지" 규칙에서 예외로 둔다. §76에서 미캠회관 제외를 다룰 때와 같은 성격의
# 요청이 또 나와, 이참에 세 코너를 한 곳에 묶는다.
LOW_HEADCOUNT_EXEMPT_CORNER_NAMES = frozenset({SNAP_SNACK_CORNER_NAME, "그린미트", MICAM_HALL_CORNER_NAME})

# §91(2026-08): 담당자가 준 리포트 양식의 코너 등장 순서 — 여러 화면(코너 목록·
# 필터·차트 색상 배정·표 정렬)에 공통으로 적용한다. 화면마다 알파벳/corner_id/
# 무순서로 제각각이던 걸 하나로 통일한다. 이 목록에 없는 코너(테스트 코너,
# 폐지된 코너 등)는 뒤에 corner_id 순으로 붙는다 — corner_display_sort_key 참고.
CORNER_DISPLAY_ORDER: tuple[str, ...] = (
    "도담찌개",
    "고슬고슬비빈",
    "싱푸차이나",
    "모던키친",
    "동방식객",
    "한식사계",
    SNAP_SNACK_CORNER_NAME,
    TAKE_OUT_CORNER_NAME,
)


def corner_display_sort_key(corner_id: int, corner_name: str) -> tuple[int, int]:
    """§91: 코너를 CORNER_DISPLAY_ORDER 순서로 정렬하기 위한 키.

    목록에 있는 코너는 그 순번을, 없는 코너는 목록 길이(=항상 목록에 있는
    코너들보다 큼)를 1차 키로 써서 전부 뒤로 보낸다. 목록 밖 코너끼리는
    corner_id 오름차순(이 저장소에서 지금까지 "코너 마스터 목록"의 사실상
    기본 순서로 쓰여 온 값, `GET /analysis/corners/list`의 기존 정렬 기준)으로
    2차 정렬한다. 이미 다른 기준(식수 desc, core_employee_count desc 등)으로
    랭킹하는 화면은 그 랭킹 기준을 1차로 유지하고, 이 키는 동점 처리(tiebreak)
    용으로만 쓴다 — 랭킹 자체의 목적을 훼손하지 않기 위함.
    """
    try:
        rank = CORNER_DISPLAY_ORDER.index(corner_name)
    except ValueError:
        rank = len(CORNER_DISPLAY_ORDER)
    return (rank, corner_id)


CORNER_ALIAS_GROUPS = (
    (TAKE_OUT_CORNER_NAME, TAKE_OUT_ALIASES),
    (SNAP_SNACK_CORNER_NAME, SNAP_SNACK_ALIASES),
)

# 코너 별칭 → 대표 이름. 그룹이 늘어도 _normalize_corner_name이 하나의 조회로
# 처리하도록 여기서 한 번만 평탄화한다.
CORNER_ALIAS_MAP: dict[str, str] = {
    alias: canonical for canonical, aliases in CORNER_ALIAS_GROUPS for alias in aliases
}

# 대표 이름 + 모든 별칭을 합친 집합 — 메뉴명 끝에 "(코너명)"으로 붙어 들어오는
# 걸 지울 때 쓴다(menu_name.py, 2026-08). 대표 이름도 포함해야 이미 대표 이름
# 그대로 붙어 들어온 경우("진짬뽕라면(스냅스낵)")도 걸러진다.
ALL_CORNER_NAMES: frozenset[str] = frozenset(
    name for canonical, aliases in CORNER_ALIAS_GROUPS for name in ({canonical} | aliases)
)
