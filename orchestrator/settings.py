"""Single place for configuration.

Everything that used to be repeated in several files lives here:
  - loading config.yaml
  - the LLM model name (environment variable first, then config.yaml)
  - the API key
  - where the Blender program is installed

Nothing in this module needs Blender to be installed.
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Used only if config.yaml is missing or has no llm.default_model.
# The real default lives in config.yaml. VERIFY the current model name there.
FALLBACK_MODEL = "claude-sonnet-5-5"

# Places to look for Blender when BLENDER_EXE is not set and config.yaml has no valid path.
_COMMON_BLENDER_PATHS = [
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
]


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load config.yaml.

    Search order: the explicit path, ./config.yaml, then <project root>/config.yaml.
    Returns an empty dict if no file is found.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(Path("config.yaml"))
    candidates.append(PROJECT_ROOT / "config.yaml")
    for candidate in candidates:
        if candidate.is_file():
            with open(candidate, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def get_model_name(cfg: Optional[Dict[str, Any]] = None) -> str:
    """LLM model name: environment variable, then config.yaml, then FALLBACK_MODEL."""
    cfg = load_config() if cfg is None else cfg
    llm_cfg = cfg.get("llm", {}) or {}
    env_var = llm_cfg.get("model_env_var", "LLM_MODEL")
    return os.environ.get(env_var) or llm_cfg.get("default_model") or FALLBACK_MODEL


def get_api_key(cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """API key from the environment variable named in config.yaml (default ANTHROPIC_API_KEY)."""
    cfg = load_config() if cfg is None else cfg
    llm_cfg = cfg.get("llm", {}) or {}
    env_var = llm_cfg.get("api_key_env_var", "ANTHROPIC_API_KEY")
    return os.environ.get(env_var)


def get_blender_exe(cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Find the Blender program, or return None.

    Order: BLENDER_EXE environment variable, paths.blender_exe in config.yaml,
    `blender` on PATH, then a few common install locations.
    """
    env_value = os.environ.get("BLENDER_EXE")
    if env_value:
        return env_value

    cfg = load_config() if cfg is None else cfg
    configured = (cfg.get("paths", {}) or {}).get("blender_exe")
    if configured and Path(configured).is_file():
        return str(configured)

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    for candidate in _COMMON_BLENDER_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None
