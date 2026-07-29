import json

import config as config_module
from config import load_config


def _write_config(tmp_path, monkeypatch, data: dict):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(config_module, "_CONFIG_PATH", path)
    monkeypatch.delenv("INGEST_BACKEND_URL", raising=False)
    monkeypatch.delenv("INGEST_API_TOKEN", raising=False)
    monkeypatch.delenv("INGEST_EMPLOYEE_MAPPING_PATH", raising=False)
    monkeypatch.delenv("INGEST_VERIFY_SSL", raising=False)


def test_verify_ssl_defaults_to_true(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {"backend_base_url": "http://x/api", "api_token": "t"})
    assert load_config().verify_ssl is True


def test_verify_ssl_false_from_config_file(tmp_path, monkeypatch):
    _write_config(
        tmp_path, monkeypatch, {"backend_base_url": "http://x/api", "api_token": "t", "verify_ssl": False}
    )
    assert load_config().verify_ssl is False


def test_verify_ssl_env_var_overrides_file(tmp_path, monkeypatch):
    _write_config(
        tmp_path, monkeypatch, {"backend_base_url": "http://x/api", "api_token": "t", "verify_ssl": True}
    )
    monkeypatch.setenv("INGEST_VERIFY_SSL", "false")
    assert load_config().verify_ssl is False


def test_employee_mapping_path_defaults_to_none(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {"backend_base_url": "http://x/api", "api_token": "t"})
    assert load_config().employee_mapping_path is None
