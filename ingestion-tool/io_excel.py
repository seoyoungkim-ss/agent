"""PRD 9.2: 나스카(DRM)로 보호된 파일을 실제 Excel 인스턴스로 열어 값을 읽는다.

DRM은 승인된 애플리케이션(Excel)이 열 때만 복호화하므로, openpyxl/pandas로
원문을 직접 읽을 수 없다. xlwings로 Excel을 구동해 셀 값을 메모리로 옮긴 뒤
곧바로 워크북을 닫는다 — 이 함수를 통과하면 이후 로직(parsing/*)은 이미
평범한 파이썬 값(list of lists)만 다루므로 DRM과 무관해진다.

이 모듈은 Windows + Excel + 나스카가 설치된 환경에서만 동작한다. Linux 개발
환경에서는 xlwings import 자체가 실패하므로, 실제 실행은 운영자 PC에서만
검증 가능하다(parsing/ 쪽 로직은 tests/에서 그리드를 직접 만들어 검증한다).
"""

from typing import Any


def read_used_range(path: str, sheet_name: str | None = None) -> list[list[Any]]:
    """엑셀 파일의 (첫 번째 또는 지정한) 시트에서 사용된 범위를 그리드로 읽어온다."""
    try:
        import xlwings as xw
    except ImportError as exc:  # pragma: no cover - Windows 전용 경로
        raise RuntimeError(
            "xlwings를 불러올 수 없습니다. 이 도구는 Excel + 나스카가 설치된 "
            "Windows 운영자 PC에서만 실행할 수 있습니다."
        ) from exc

    app = xw.App(visible=False)
    try:
        wb = app.books.open(path)
        try:
            sheet = wb.sheets[sheet_name] if sheet_name else wb.sheets[0]
            values = sheet.used_range.value
            if values and not isinstance(values[0], list):
                # 시트에 단일 행/열만 있으면 xlwings가 1차원 리스트를 반환하므로
                # 파서가 기대하는 2차원 그리드로 맞춰준다.
                values = [values]
            return values or []
        finally:
            wb.close()
    finally:
        app.quit()
