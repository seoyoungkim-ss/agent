"""사번 ↔ Knox ID 매핑 (merge.py 참고: A사 인원은 사번==Knox ID라 매핑 없이도
일치하지만, 그 외 회사는 두 값 체계가 달라 별도 매핑이 필요하다).

이 매핑 파일은 운영자가 로컬에 직접 만들어 관리하는 참조용 파일이다. 나스카(DRM)
대상인 공식 사내 시스템 산출물이 아니라고 가정하지만, 두 가지 형식을 모두
지원한다:

- **.csv**: 표준 csv 모듈로 직접 읽는다(xlwings/Excel 불필요, Linux에서도 테스트
  가능). 헤더 필수, 순서 무관:
      사번,knox_id
      12345678,abcd1234
- **.xlsx/.xls**: `io_excel.read_used_range()`(xlwings)로 읽는다 — 엑셀은 내부
  적으로 유니코드라 CSV에서 흔한 인코딩 문제(CP949 vs UTF-8)를 아예 피할 수 있어,
  한글 헤더/값 때문에 CSV가 깨지면 이 형식으로 저장해서 쓰면 된다. 첫 행은 헤더
  (역시 "사번", "knox_id" 컬럼 필요, 순서 무관 — 헤더 이름으로 찾음).
"""

import csv
from pathlib import Path
from typing import Any

# 한글 Windows에서 Excel로 "다른 이름으로 저장 > CSV"를 하면 기본값이 UTF-8이
# 아니라 CP949(확장 EUC-KR)라, UTF-8만 시도하면 한글 헤더/값에서
# UnicodeDecodeError가 난다. 순서대로 시도해 처음 성공하는 인코딩을 쓴다.
_ENCODINGS_TO_TRY = ("utf-8-sig", "cp949")


def load_employee_mapping(path: str | None) -> dict[str, str]:
    """사번 -> knox_id 매핑 딕셔너리를 반환한다.

    path가 비어있거나 파일이 없으면 빈 dict를 반환한다 — 매핑이 없는 환경(A사만
    다루는 경우 등)에서도 에러 없이 그냥 매핑 미사용으로 동작하게 하려는 의도.
    확장자로 csv/엑셀을 구분한다.
    """
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}

    if file_path.suffix.lower() == ".csv":
        return _load_from_csv(file_path)
    return _load_from_excel(file_path)


def _load_from_csv(file_path: Path) -> dict[str, str]:
    last_error: UnicodeDecodeError | None = None
    for encoding in _ENCODINGS_TO_TRY:
        try:
            with file_path.open(encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                return {
                    employee_id: knox_id
                    for row in reader
                    if (employee_id := (row.get("사번") or "").strip())
                    and (knox_id := (row.get("knox_id") or "").strip())
                }
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise RuntimeError(
        f"{file_path}의 인코딩을 알 수 없습니다 (시도: {', '.join(_ENCODINGS_TO_TRY)}). "
        "Excel에서 '다른 이름으로 저장 > CSV UTF-8(쉼표로 분리)'로 다시 저장하거나, "
        ".xlsx로 저장해서 써보세요."
    ) from last_error


def _load_from_excel(file_path: Path) -> dict[str, str]:
    from io_excel import read_used_range

    grid = read_used_range(str(file_path))
    return _parse_mapping_grid(grid)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        # 엑셀이 사번/Knox ID처럼 숫자로만 된 문자열을 자동으로 숫자로 인식해
        # 12345678.0처럼 넘기는 경우가 있다 — 정수라면 소수점을 떼고 문자열화.
        return str(int(value))
    return str(value).strip()


def _parse_mapping_grid(grid: list[list[Any]]) -> dict[str, str]:
    """xlsx에서 읽은 그리드를 파싱한다 — 순수 함수라 Linux에서도 테스트 가능."""
    if not grid:
        return {}
    header = [_clean_cell(h) for h in grid[0]]
    if "사번" not in header or "knox_id" not in header:
        return {}
    id_idx = header.index("사번")
    knox_idx = header.index("knox_id")

    mapping: dict[str, str] = {}
    for row in grid[1:]:
        if len(row) <= max(id_idx, knox_idx):
            continue
        employee_id = _clean_cell(row[id_idx])
        knox_id = _clean_cell(row[knox_idx])
        if employee_id and knox_id:
            mapping[employee_id] = knox_id
    return mapping
