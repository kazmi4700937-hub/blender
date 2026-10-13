"""Choose a geometry provider by name. Add a provider by registering a class here."""

import os
from typing import Any, Dict, Optional, Type

from .base import GeometryError, GeometryProvider
from .manual import ManualProvider
from .tripo import TripoProvider

PROVIDERS: Dict[str, Type[GeometryProvider]] = {
    ManualProvider.name: ManualProvider,
    TripoProvider.name: TripoProvider,
}

DEFAULT_PROVIDER = "manual"


def provider_name(cfg: Optional[Dict[str, Any]] = None) -> str:
    """GEOMETRY_PROVIDER environment variable, then geometry.provider in config.yaml, then 'manual'."""
    if cfg is None:
        from ..settings import load_config
        cfg = load_config()
    return (os.environ.get("GEOMETRY_PROVIDER")
            or (cfg.get("geometry", {}) or {}).get("provider")
            or DEFAULT_PROVIDER)


def get_provider(name: Optional[str] = None, cfg: Optional[Dict[str, Any]] = None, **kwargs) -> GeometryProvider:
    if cfg is None:
        from ..settings import load_config
        cfg = load_config()
    name = name or provider_name(cfg)
    cls = PROVIDERS.get(name)
    if cls is None:
        raise GeometryError(f"Unknown geometry provider '{name}'. Available: {', '.join(sorted(PROVIDERS))}.")
    provider_cfg = (cfg.get("geometry", {}) or {}).get(name, {}) or {}
    return cls(provider_cfg, **kwargs)
