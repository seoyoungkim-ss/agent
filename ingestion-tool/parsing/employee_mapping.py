"""사번 ↔ Knox ID 매핑 (merge.py 참고: A사 인원은 사번==Knox ID라 매핑 없이도
일치하지만, 그 외 회사는 두 값 체계가 달라 별도 매핑이 필요하다).

이 매핑 파일은 운영자가 로컬에 직접 만들어 관리하는 참조용 CSV다. 나스카(DRM)
대상인 공식 사내 시스템 산출물이 아니라고 가정하고, xlwings/Excel 없이 표준 csv
모듈로 직접 읽는다.

CSV 형식 (헤더 필수, 순서 무관):
    사번,knox_id
    12345678,abcd1234
"""

import csv
from pathlib import Path


def load_employee_mapping(path: str | None) -> dict[str, str]:
    """사번 -> knox_id 매핑 딕셔너리를 반환한다.

    path가 비어있거나 파일이 없으면 빈 dict를 반환한다 — 매핑이 없는 환경(A사만
    다루는 경우 등)에서도 에러 없이 그냥 매핑 미사용으로 동작하게 하려는 의도.
    """
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}

    mapping: dict[str, str] = {}
    with file_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            employee_id = (row.get("사번") or "").strip()
            knox_id = (row.get("knox_id") or "").strip()
            if employee_id and knox_id:
                mapping[employee_id] = knox_id
    return mapping
