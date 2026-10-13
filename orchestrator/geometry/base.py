"""Common pieces for every geometry provider (the part that turns 2D images into a 3D model).

The rest of the app only talks to GeometryProvider. Which service does the work is a setting
(geometry.provider in config.yaml, or the GEOMETRY_PROVIDER environment variable), so changing
service never means changing the pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class GeometryError(Exception):
    """Raised when a provider cannot produce or find a model. The message is meant to be read by the user."""


@dataclass
class GeometryRequest:
    """What the app asks a provider for."""
    image_paths: List[str]                 # reference images (front first)
    output_dir: str                        # where the model files are saved
    rig: bool = False                      # also ask the provider to rig the model, if it can
    options: Dict[str, Any] = field(default_factory=dict)   # provider specific extras


@dataclass
class GeometryResult:
    """What a provider returns. Paths point at files saved in the request's output_dir."""
    provider: str
    mesh_path: str                         # the generated (unrigged) model
    rigged_path: Optional[str] = None      # a rigged copy, if the provider made one
    task_ids: Dict[str, str] = field(default_factory=dict)
    credits_used: Optional[float] = None   # None when the provider does not report cost
    notes: List[str] = field(default_factory=list)   # things the user should know (estimates, limits)


class GeometryProvider(ABC):
    """One way of getting a 3D model for a set of reference images."""

    name: str = "base"
    # What this provider can do. Used to explain a refusal instead of failing half way.
    can_generate: bool = True
    can_rig: bool = False

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}

    @abstractmethod
    def generate(self, request: GeometryRequest) -> GeometryResult:
        """Return a model for the request, or raise GeometryError."""
