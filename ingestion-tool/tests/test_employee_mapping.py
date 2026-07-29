from parsing.employee_mapping import load_employee_mapping


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
