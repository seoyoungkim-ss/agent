import pytest

from parsing.employee_mapping import _parse_mapping_grid, load_employee_mapping


def test_loads_mapping_from_csv(tmp_path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text("사번,knox_id\n12345678,abcd1234\n87654321,wxyz9999\n", encoding="utf-8")

    mapping = load_employee_mapping(str(csv_path))
    assert mapping == {"12345678": "abcd1234", "87654321": "wxyz9999"}


def test_missing_path_returns_empty_dict():
    assert load_employee_mapping(None) == {}
    assert load_employee_mapping("") == {}


def test_nonexistent_file_returns_empty_dict(tmp_path):
    assert load_employee_mapping(str(tmp_path / "없는파일.csv")) == {}


def test_blank_rows_and_whitespace_skipped(tmp_path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text("사번,knox_id\n  12345678  ,  abcd1234  \n,missing_id\nnoknox,\n", encoding="utf-8")

    mapping = load_employee_mapping(str(csv_path))
    assert mapping == {"12345678": "abcd1234"}


def test_utf8_bom_handled(tmp_path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_bytes("사번,knox_id\n12345678,abcd1234\n".encode("utf-8-sig"))

    mapping = load_employee_mapping(str(csv_path))
    assert mapping == {"12345678": "abcd1234"}


def test_cp949_encoded_csv_handled(tmp_path):
    # 한글 Windows Excel의 "CSV(쉼표로 분리)" 기본 저장 인코딩(CP949) 재현
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_bytes("사번,knox_id\n12345678,abcd1234\n".encode("cp949"))

    mapping = load_employee_mapping(str(csv_path))
    assert mapping == {"12345678": "abcd1234"}


def test_undecodable_csv_raises_helpful_error(tmp_path):
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_bytes(b"\x80\x81\x82\x83\xff\xfe")

    with pytest.raises(RuntimeError):
        load_employee_mapping(str(csv_path))


def test_parse_mapping_grid_matches_header_by_name():
    # 열 순서가 knox_id, 사번으로 뒤바뀌어도 헤더 이름으로 찾아야 함
    grid = [["knox_id", "사번"], ["abcd1234", "12345678"]]
    assert _parse_mapping_grid(grid) == {"12345678": "abcd1234"}


def test_parse_mapping_grid_converts_excel_numeric_ids_to_strings():
    # 엑셀이 숫자로만 된 사번/Knox ID를 float로 자동 변환해 넘기는 경우
    grid = [["사번", "knox_id"], [12345678.0, 87654321.0]]
    assert _parse_mapping_grid(grid) == {"12345678": "87654321"}


def test_parse_mapping_grid_missing_headers_returns_empty():
    grid = [["employee_id", "id"], ["12345678", "abcd1234"]]
    assert _parse_mapping_grid(grid) == {}


def test_parse_mapping_grid_empty_returns_empty():
    assert _parse_mapping_grid([]) == {}
