from __future__ import annotations
import json
from pathlib import Path
from platformdirs import user_config_dir

APP_NAME = "deepseek"
APP_AUTHOR = "deepseek"
CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_MODEL = "deepseek-chat"
SUPPORTED_MODELS = ["deepseek-chat", "deepseek-reasoner"]
DEFAULT_BASEURL = "https://api.deepseek.com"

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def normalize_with_defaults(cfg: dict) -> dict:
    if not cfg.get("base_url"):
        cfg["base_url"] = DEFAULT_BASEURL
    if not cfg.get("model"):
        cfg["model"] = DEFAULT_MODEL
    return cfg
