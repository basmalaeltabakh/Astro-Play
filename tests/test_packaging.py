"""Paths used by the packaged (PyInstaller) build: game files from the bundle, saves in a per-user folder."""
import importlib
import sys
from pathlib import Path

from astro import config


def _reload_frozen(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "data").mkdir(parents=True)
    (bundle / "data" / "settings.json").write_text('{"lang": "ar"}', encoding="utf-8")
    for var in ("ASTRO_DB_PATH", "ASTRO_CHROMA_DIR", "ASTRO_SETTINGS_PATH", "ASTRO_DONKI_CACHE", "ASTRO_OSDR_CACHE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return bundle, importlib.reload(config)


def test_frozen_build_reads_bundle_and_writes_user_folder(monkeypatch, tmp_path):
    try:
        bundle, cfg = _reload_frozen(monkeypatch, tmp_path)
        user = Path(cfg.USER_DIR)
        assert cfg.FROZEN
        assert cfg.ASSETS_DIR == bundle / "assets"
        assert cfg.OSDR_STUDIES_PATH == bundle / "data" / "osdr_studies.json"
        assert cfg.DONKI_ARCHIVE_PATH == bundle / "data" / "donki_archive.json"
        assert str(user).startswith(str(tmp_path)) and user.is_dir()
        for p in (cfg.DB_PATH, cfg.CHROMA_DIR, cfg.SETTINGS_PATH, cfg.DONKI_CACHE_PATH, cfg.OSDR_CACHE_PATH):
            assert Path(p).parent == user, p
        assert cfg.SETTINGS_PATH.read_text(encoding="utf-8") == '{"lang": "ar"}'   # seeded on first run
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_source_run_keeps_project_paths():
    assert not config.FROZEN
    assert config.USER_DIR == config.DATA_DIR == config.ROOT / "data"
