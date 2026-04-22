"""Configuration loader for 1C Helper Desktop Agent.

Stores config in %APPDATA%\\net1c-agent\\config.json (Windows) or ~/.config/net1c-agent/config.json.
Holds:
  server_url  - https://net1c.ru
  agent_id    - uuid
  token       - bearer token (secret!)
  store_id    - store this agent belongs to
  name        - human-readable name (e.g. "Касса 1")
"""
import json
import os
import platform
import sys
from pathlib import Path
from typing import Optional


AGENT_VERSION = "0.1.0"
DEFAULT_SERVER = "https://net1c.ru"


def get_config_dir() -> Path:
    """Platform-specific user config dir."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "net1c-agent"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "net1c-agent"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "net1c-agent"


CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
BROWSER_DATA_DIR = CONFIG_DIR / "browser-profile"
LOG_DIR = CONFIG_DIR / "logs"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots"


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: dict) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # restrict permissions on POSIX
    if platform.system() != "Windows":
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass


def is_paired() -> bool:
    cfg = load()
    return bool(cfg.get("token") and cfg.get("agent_id"))


def get_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


def get_platform() -> str:
    return f"{platform.system()} {platform.release()}"
