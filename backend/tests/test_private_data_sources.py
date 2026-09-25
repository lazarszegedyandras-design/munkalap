from pathlib import Path
from types import SimpleNamespace

from app.importers import customer_assets
from app.services import company_profiles, hr_import


def test_missing_private_sources_do_not_load_real_data(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(customer_assets, "source_file", lambda: missing)
    monkeypatch.setattr(hr_import, "source_file", lambda: missing)
    monkeypatch.setattr(company_profiles, "company_profiles_path", lambda: missing)

    assert customer_assets.source_available() is False
    assert customer_assets.load_builtin_rows() == []
    assert hr_import.source_available() is False
    assert hr_import.ensure_rlb_2026_staging(None) == []
    assert company_profiles.load_company_profiles() == {}


def test_runtime_private_sources_take_priority(monkeypatch, tmp_path):
    monkeypatch.setattr(customer_assets, "get_settings", lambda: SimpleNamespace(runtime_dir=str(tmp_path)))
    monkeypatch.setattr(hr_import, "get_settings", lambda: SimpleNamespace(runtime_dir=str(tmp_path)))
    monkeypatch.setattr(customer_assets, "DATA_FILE", Path("missing_customer_source.json"))
    monkeypatch.setattr(hr_import, "DATA_FILE", Path("missing_hr_source.json"))
    customer_runtime = tmp_path / "missing_customer_source.json"
    hr_runtime = tmp_path / "missing_hr_source.json"
    customer_runtime.write_text("[]", encoding="utf-8")
    hr_runtime.write_text("{}", encoding="utf-8")

    assert customer_assets.source_file() == customer_runtime
    assert customer_assets.load_builtin_rows() == []
    assert hr_import.source_file() == hr_runtime
    assert hr_import.source_available() is True
