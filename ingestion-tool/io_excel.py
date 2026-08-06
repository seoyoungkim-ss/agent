"""PRD 9.2: 나스카(DRM)로 보호된 파일을 실제 Excel 인스턴스로 열어 값을 읽는다.

DRM은 승인된 애플리케이션(Excel)이 열 때만 복호화하므로, openpyxl/pandas로
원문을 직접 읽을 수 없다. xlwings로 Excel을 구동해 셀 값을 메모리로 옮긴 뒤
곧바로 워크북을 닫는다 — 이 함수를 통과하면 이후 로직(parsing/*)은 이미
평범한 파이썬 값(list of lists)만 다루므로 DRM과 무관해진다.

이 모듈은 Windows + Excel + 나스카가 설치된 환경에서만 동작한다. Linux 개발
환경에서는 xlwings import 자체가 실패하므로, 실제 실행은 운영자 PC에서만
검증 가능하다(parsing/ 쪽 로직은 tests/에서 그리드를 직접 만들어 검증한다).
"""

from contextlib import contextmanager
from typing import Any


def _import_xlwings():
    try:
        import xlwings as xw
    except ImportError as exc:  # pragma: no cover - Windows 전용 경로
        raise RuntimeError(
            "xlwings를 불러올 수 없습니다. 이 도구는 Excel + 나스카가 설치된 "
            "Windows 운영자 PC에서만 실행할 수 있습니다."
        ) from exc
    return xw


@contextmanager
def excel_session():  # pragma: no cover - Windows 전용 경로
    """Excel 인스턴스 하나를 열어 여러 파일에 재사용한다 (2026-08).

    파일 하나당 `xw.App()`을 띄웠다 내리면 31개 적재에 Excel이 31번 뜬다 —
    일괄 적재에선 이게 전체 시간의 대부분이다.

    ⚠️ **반드시 `with`로만 쓴다.** App을 재사용하려고 수명을 늘린 만큼,
    정리를 놓치면 운영자 PC에 `EXCEL.EXE`가 남는다. 배치를 몇 번 돌리면
    보이지 않는 Excel 프로세스가 쌓여 PC가 느려지고, 그 파일들이 잠긴다.
    """
    xw = _import_xlwings()
    app = xw.App(visible=False)
    try:
        yield app
    finally:
        app.quit()


def read_used_range(path: str, sheet_name: str | None = None, *, app: Any = None) -> list[list[Any]]:
    """엑셀 파일의 (첫 번째 또는 지정한) 시트에서 사용된 범위를 그리드로 읽어온다.

    `app`을 주면 그 Excel 인스턴스를 빌려 쓰고 **닫지 않는다**(수명은 준 쪽,
    즉 `excel_session()`이 책임진다). 생략하면 지금까지처럼 자기 인스턴스를
    띄웠다 내리므로 **기존 호출부 동작은 그대로다.**
    """
    if app is not None:
        return _read_with_app(app, path, sheet_name)

    xw = _import_xlwings()
    own_app = xw.App(visible=False)
    try:
        return _read_with_app(own_app, path, sheet_name)
    finally:
        own_app.quit()


def _read_with_app(app: Any, path: str, sheet_name: str | None) -> list[list[Any]]:
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
        # 파싱이 터져도 워크북은 닫는다 — 안 닫으면 다음 파일에서 잠금 충돌이 난다.
        wb.close()
