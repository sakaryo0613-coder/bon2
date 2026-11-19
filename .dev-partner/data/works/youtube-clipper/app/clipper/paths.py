"""置き場所の解決。ソースから動かす場合と、PyInstaller で固めたアプリ（clipper.exe）の両方に対応する。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)
IS_WIN = os.name == "nt"


def resource_dir() -> Path:
    """同梱物のルート。アプリでは展開先（_MEIPASS）、ソースでは app/ フォルダ。"""
    return Path(getattr(sys, "_MEIPASS", PKG.parent))


def resource(rel: str) -> Path:
    return resource_dir() / rel


def fonts_dir() -> Path:
    return resource("clipper/fonts")


def samples_dir() -> Path:
    """合格基準用のサンプル。アプリでは同梱、ソースでは works/youtube-clipper/samples。"""
    p = resource("samples")
    return p if p.exists() else PKG.parent.parent / "samples"


def bin_dir() -> Path:
    """同梱の ffmpeg/ffprobe（アプリのみ）。"""
    return resource("ffmpeg")


def _win_env(name: str, fallback: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else fallback


def home_dir() -> Path:
    """作業フォルダの置き場所（既定はドキュメント\\clipper）。"""
    if os.environ.get("CLIPPER_HOME"):
        return Path(os.environ["CLIPPER_HOME"])
    return Path.home() / "Documents" / "clipper"


def app_data_dir() -> Path:
    """設定の置き場所（%APPDATA%\\clipper、Linux/Mac は ~/.config/clipper）。"""
    if os.environ.get("CLIPPER_CONFIG_DIR"):
        return Path(os.environ["CLIPPER_CONFIG_DIR"])
    return _win_env("APPDATA", Path.home() / ".config") / "clipper"


def local_data_dir() -> Path:
    """モデル・ログ・起動情報の置き場所（%LOCALAPPDATA%\\clipper、Linux/Mac は ~/.cache/clipper）。"""
    if os.environ.get("CLIPPER_LOCAL_DIR"):
        return Path(os.environ["CLIPPER_LOCAL_DIR"])
    return _win_env("LOCALAPPDATA", Path.home() / ".cache") / "clipper"


def models_dir() -> Path:
    return local_data_dir() / "models"


# ---------------------------------------------------------------- 設定
def load_config() -> dict:
    p = app_data_dir() / "config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def setup_env() -> None:
    """同梱の ffmpeg を PATH の先頭に入れ、設定の APIキーを環境変数に入れる（未設定のときだけ）。"""
    b = bin_dir()
    if b.exists():
        os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
    key = load_config().get("api_key")
    if key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = key
