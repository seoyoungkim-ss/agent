"""weekly-menu-batch — 파일 수집과 전송 흐름.

xlwings는 Windows 전용이라 여기서 실제 엑셀은 못 연다. `read_used_range`와
`excel_session`을 갈아끼워 그리드를 직접 주입하면 나머지 전 구간(수집 → 주차
인식 → 파싱 → 미리보기 → 업로드 페이로드)은 검증할 수 있다.
"""

import contextlib
import datetime as dt

import pytest

import cli
import upload

TODAY = dt.date(2026, 8, 6)


def _grid(day_cells):
    header = ["구분", "코너", None]
    for cell in day_cells:
        header += [cell, None]
    main = ["중식", "한식", None] + ["제육볶음", None] * 6
    side = [None, None, None] + ["김치", None] * 6
    return [[None] * 15, header, main, side]


JULY = _grid(["7/6(월)", "7/7(화)", "7/8(수)", "7/9(목)", "7/10(금)", "7/11(토)"])
NO_DATES = _grid(["월", "화", "수", "목", "금", "토"])


# ---------------------------------------------------------------------------
# 파일 수집
# ---------------------------------------------------------------------------


def test_collect_skips_excel_lock_files(tmp_path):
    """`~$`는 엑셀이 파일을 열어둘 때 만드는 잠금 파일이다.

    운영자가 식단표를 열어둔 채 배치를 돌리는 건 흔한 일이라, 안 거르면 매번
    깨진 파일로 실패한다.
    """
    (tmp_path / "식단표.xlsx").write_text("")
    (tmp_path / "~$식단표.xlsx").write_text("")
    assert [p.name for p in cli._collect_menu_files(tmp_path, recursive=False)] == ["식단표.xlsx"]


def test_collect_ignores_non_excel_files(tmp_path):
    (tmp_path / "a.xlsx").write_text("")
    (tmp_path / "메모.txt").write_text("")
    (tmp_path / "b.xlsm").write_text("")
    assert [p.name for p in cli._collect_menu_files(tmp_path, recursive=False)] == ["a.xlsx", "b.xlsm"]


def test_collect_is_sorted_for_deterministic_output(tmp_path):
    for name in ("c.xlsx", "a.xlsx", "b.xlsx"):
        (tmp_path / name).write_text("")
    assert [p.name for p in cli._collect_menu_files(tmp_path, recursive=False)] == [
        "a.xlsx",
        "b.xlsx",
        "c.xlsx",
    ]


def test_collect_recursive_only_when_asked(tmp_path):
    (tmp_path / "위.xlsx").write_text("")
    sub = tmp_path / "하위"
    sub.mkdir()
    (sub / "아래.xlsx").write_text("")
    assert len(cli._collect_menu_files(tmp_path, recursive=False)) == 1
    assert len(cli._collect_menu_files(tmp_path, recursive=True)) == 2


# ---------------------------------------------------------------------------
# 전송 흐름
# ---------------------------------------------------------------------------


@pytest.fixture
def batch_env(monkeypatch, tmp_path):
    """엑셀 읽기를 그리드 주입으로 바꾸고, 전송 페이로드를 모은다."""
    grids: dict[str, list] = {}
    payloads: list[dict] = []

    monkeypatch.setattr(cli, "excel_session", lambda: contextlib.nullcontext("FAKE"))
    monkeypatch.setattr(
        cli,
        "read_used_range",
        lambda path, sheet_name=None, app=None: grids[path.rsplit("/", 1)[-1]],
    )
    monkeypatch.setattr(
        upload, "_post_with_retry", lambda client, url, payload: payloads.append(payload)
    )
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: type("C", (), {"backend_base_url": "https://x/api", "api_token": "t", "verify_ssl": True})(),
    )

    def add(name, grid):
        (tmp_path / name).write_text("")
        grids[name] = grid

    return type("Env", (), {"dir": str(tmp_path), "add": staticmethod(add), "payloads": payloads})


def test_dry_run_sends_nothing(batch_env):
    """처음엔 --dry-run으로 주 매핑부터 확인하라고 안내한다 — 정말 안 보내야 한다."""
    batch_env.add("2026-07-06.xlsx", JULY)
    assert cli.main(["weekly-menu-batch", batch_env.dir, "--dry-run"]) == 0
    assert batch_env.payloads == []


def test_batch_always_replaces_existing_weeks(batch_env):
    """폴더째 올리면 이미 적재된 주가 섞이는 게 정상이다 — 안 켜면 행이 2배가 된다."""
    batch_env.add("2026-07-06.xlsx", JULY)
    assert cli.main(["weekly-menu-batch", batch_env.dir, "--yes"]) == 0
    assert all(p["replace_existing"] is True for p in batch_env.payloads)


def test_week_start_comes_from_the_sheet_not_the_filename(batch_env):
    """파일명이 엉뚱해도 시트 헤더가 이긴다 — 파일명 규칙에 안 얽매인다."""
    batch_env.add("이름은아무거나.xlsx", JULY)
    cli.main(["weekly-menu-batch", batch_env.dir, "--yes"])
    dates = {r["plan_date"] for p in batch_env.payloads for r in p["rows"]}
    assert min(dates) == "2026-07-06"


def test_one_unreadable_file_does_not_stop_the_rest(batch_env, capsys):
    """31개 중 하나가 이상하다고 나머지 30개를 못 올리면 안 된다."""
    batch_env.add("정상.xlsx", JULY)
    batch_env.add("날짜없음.xlsx", NO_DATES)
    assert cli.main(["weekly-menu-batch", batch_env.dir, "--yes"]) == 0
    assert len(batch_env.payloads) == 1
    out = capsys.readouterr().out
    assert "건너뛴 파일 1개" in out
    assert "날짜없음.xlsx" in out


def test_each_file_is_uploaded_separately_for_failure_isolation(batch_env):
    """파일 단위로 보내야 실패 시 어느 주가 안 올라갔는지 바로 안다."""
    batch_env.add("a.xlsx", JULY)
    batch_env.add(
        "b.xlsx", _grid(["7/13(월)", "7/14(화)", "7/15(수)", "7/16(목)", "7/17(금)", "7/18(토)"])
    )
    cli.main(["weekly-menu-batch", batch_env.dir, "--yes"])
    assert len(batch_env.payloads) == 2


def test_duplicate_weeks_are_warned_because_later_file_wins(batch_env, capsys):
    """같은 주를 가리키는 파일이 둘이면 슬롯 교체라 뒤 파일이 앞을 덮는다."""
    batch_env.add("a.xlsx", JULY)
    batch_env.add("b_같은주.xlsx", JULY)
    cli.main(["weekly-menu-batch", batch_env.dir, "--dry-run"])
    assert "같은 주를 가리키는 파일이 여러 개" in capsys.readouterr().out


def test_empty_directory_exits_nonzero(batch_env):
    assert cli.main(["weekly-menu-batch", batch_env.dir, "--yes"]) == 1


def test_nonexistent_directory_exits_nonzero(tmp_path):
    assert cli.main(["weekly-menu-batch", str(tmp_path / "없는폴더"), "--yes"]) == 1
