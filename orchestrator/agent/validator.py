"""
Validator for LLM tool calls.
Enforces parameter bounds, detects unknown tools, fills in defaults,
and generates canonical Blender bridge commands.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from .tools import AVAILABLE_MOTIONS, TOOL_DEFAULTS, TOOL_ALIASES

@dataclass
class ValidationResult:
    valid: bool
    tool_name: str
    canonical_tool: str = ""
    sanitized_args: Dict[str, Any] = field(default_factory=dict)
    applied_defaults: Dict[str, Any] = field(default_factory=dict)
    bridge_command: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    message: str = ""

def format_unknown_tool_message(tool_name: str) -> str:
    motions_str = ", ".join(AVAILABLE_MOTIONS)
    return (
        f"I cannot perform '{tool_name}'. Available character motions are: {motions_str}. "
        "Available environment tools: build_environment, set_frame_range."
    )

def validate_tool_call(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> ValidationResult:
    """
    Validates a tool call and its arguments.
    Returns ValidationResult with status, errors, sanitized args, defaults, and bridge command.
    """
    if arguments is None:
        arguments = {}

    # Handle raw apply_motion call (e.g. {"name": "jump", "params": {...}})
    if tool_name == "apply_motion":
        motion_name = arguments.get("name", "").lower()
        if not motion_name or motion_name not in AVAILABLE_MOTIONS:
            motions_str = ", ".join(AVAILABLE_MOTIONS)
            msg = f"Motion '{motion_name}' is not supported. Available motions are: {motions_str}."
            return ValidationResult(
                valid=False,
                tool_name=tool_name,
                canonical_tool=tool_name,
                errors=[msg],
                message=msg
            )
        # Normalize to canonical motion tool name
        tool_name = f"apply_motion_{motion_name}"
        arguments = arguments.get("params", {}) or {}

    # Normalize aliases (e.g. 'jump' -> 'apply_motion_jump')
    canonical_name = TOOL_ALIASES.get(tool_name, tool_name)

    if canonical_name not in TOOL_DEFAULTS:
        msg = format_unknown_tool_message(tool_name)
        return ValidationResult(
            valid=False,
            tool_name=tool_name,
            canonical_tool=canonical_name,
            errors=[f"Unknown tool or motion: '{tool_name}'"],
            message=msg
        )

    errors: List[str] = []
    defaults = TOOL_DEFAULTS[canonical_name]
    sanitized: Dict[str, Any] = {}
    applied_defaults: Dict[str, Any] = {}

    # 1. Validation per tool type
    if canonical_name == "build_environment":
        # kind
        kind = arguments.get("kind")
        if kind is None:
            kind = defaults["kind"]
            applied_defaults["kind"] = kind
        elif kind not in ["ground", "platform_drop"]:
            errors.append(f"Invalid environment kind '{kind}'. Allowed kinds: ground, platform_drop.")
        sanitized["kind"] = str(kind)

        # height_m
        height_m = arguments.get("height_m")
        if height_m is None:
            height_m = defaults["height_m"]
            applied_defaults["height_m"] = height_m
        else:
            try:
                height_m = float(height_m)
                if height_m < 0.0:
                    errors.append(f"Platform height cannot be negative (got {height_m}m).")
            except (ValueError, TypeError):
                errors.append(f"height_m must be a numeric value, got {type(height_m).__name__}.")
        sanitized["height_m"] = height_m

        # size_m
        size_m = arguments.get("size_m")
        if size_m is None:
            size_m = defaults["size_m"]
            applied_defaults["size_m"] = size_m
        else:
            try:
                size_m = float(size_m)
                if size_m <= 0.0:
                    errors.append(f"Environment size must be greater than 0 (got {size_m}m).")
            except (ValueError, TypeError):
                errors.append(f"size_m must be a numeric value, got {type(size_m).__name__}.")
        sanitized["size_m"] = size_m

        bridge_cmd = {
            "command": "build_environment",
            "params": sanitized
        }

    elif canonical_name == "apply_motion_jump":
        # start_height_m
        start_height_m = arguments.get("start_height_m")
        if start_height_m is None:
            start_height_m = defaults["start_height_m"]
            applied_defaults["start_height_m"] = start_height_m
        else:
            try:
                start_height_m = float(start_height_m)
                if start_height_m < 0.0:
                    errors.append(f"start_height_m cannot be negative (got {start_height_m}m).")
            except (ValueError, TypeError):
                errors.append(f"start_height_m must be numeric.")
        sanitized["start_height_m"] = start_height_m

        # end_height_m
        end_height_m = arguments.get("end_height_m")
        if end_height_m is None:
            end_height_m = defaults["end_height_m"]
            applied_defaults["end_height_m"] = end_height_m
        else:
            try:
                end_height_m = float(end_height_m)
                if end_height_m < 0.0:
                    errors.append(f"end_height_m cannot be negative (got {end_height_m}m).")
            except (ValueError, TypeError):
                errors.append(f"end_height_m must be numeric.")
        sanitized["end_height_m"] = end_height_m

        # forward_distance_m
        fwd_dist = arguments.get("forward_distance_m")
        if fwd_dist is None:
            fwd_dist = defaults["forward_distance_m"]
            applied_defaults["forward_distance_m"] = fwd_dist
        else:
            try:
                fwd_dist = float(fwd_dist)
            except (ValueError, TypeError):
                errors.append(f"forward_distance_m must be numeric.")
        sanitized["forward_distance_m"] = fwd_dist

        # duration_s
        duration_s = arguments.get("duration_s")
        if duration_s is None:
            duration_s = defaults["duration_s"]
            applied_defaults["duration_s"] = duration_s
        else:
            try:
                duration_s = float(duration_s)
                if duration_s < 0.3:
                    errors.append(f"duration_s must be at least 0.3s (got {duration_s}s).")
            except (ValueError, TypeError):
                errors.append(f"duration_s must be numeric.")
        sanitized["duration_s"] = duration_s

        # fps
        fps = arguments.get("fps")
        if fps is None:
            fps = defaults["fps"]
            applied_defaults["fps"] = fps
        else:
            try:
                fps = int(fps)
                if fps < 1:
                    errors.append(f"fps must be at least 1 (got {fps}).")
            except (ValueError, TypeError):
                errors.append(f"fps must be an integer.")
        sanitized["fps"] = fps

        bridge_cmd = {
            "command": "apply_motion",
            "params": {
                "name": "jump",
                "params": sanitized
            }
        }

    elif canonical_name == "apply_motion_walk":
        # distance_m
        distance_m = arguments.get("distance_m")
        if distance_m is None:
            distance_m = defaults["distance_m"]
            applied_defaults["distance_m"] = distance_m
        else:
            try:
                distance_m = float(distance_m)
                if distance_m < 0.0:
                    errors.append(f"distance_m cannot be negative (got {distance_m}m).")
            except (ValueError, TypeError):
                errors.append(f"distance_m must be numeric.")
        sanitized["distance_m"] = distance_m

        # duration_s
        duration_s = arguments.get("duration_s")
        if duration_s is None:
            duration_s = defaults["duration_s"]
            applied_defaults["duration_s"] = duration_s
        else:
            try:
                duration_s = float(duration_s)
                if duration_s < 0.3:
                    errors.append(f"duration_s must be at least 0.3s (got {duration_s}s).")
            except (ValueError, TypeError):
                errors.append(f"duration_s must be numeric.")
        sanitized["duration_s"] = duration_s

        # fps
        fps = arguments.get("fps")
        if fps is None:
            fps = defaults["fps"]
            applied_defaults["fps"] = fps
        else:
            try:
                fps = int(fps)
                if fps < 1:
                    errors.append(f"fps must be at least 1 (got {fps}).")
            except (ValueError, TypeError):
                errors.append(f"fps must be an integer.")
        sanitized["fps"] = fps

        bridge_cmd = {
            "command": "apply_motion",
            "params": {
                "name": "walk",
                "params": sanitized
            }
        }

    elif canonical_name == "apply_motion_wave":
        # duration_s
        duration_s = arguments.get("duration_s")
        if duration_s is None:
            duration_s = defaults["duration_s"]
            applied_defaults["duration_s"] = duration_s
        else:
            try:
                duration_s = float(duration_s)
                if duration_s < 0.3:
                    errors.append(f"duration_s must be at least 0.3s (got {duration_s}s).")
            except (ValueError, TypeError):
                errors.append(f"duration_s must be numeric.")
        sanitized["duration_s"] = duration_s

        # fps
        fps = arguments.get("fps")
        if fps is None:
            fps = defaults["fps"]
            applied_defaults["fps"] = fps
        else:
            try:
                fps = int(fps)
                if fps < 1:
                    errors.append(f"fps must be at least 1 (got {fps}).")
            except (ValueError, TypeError):
                errors.append(f"fps must be an integer.")
        sanitized["fps"] = fps

        bridge_cmd = {
            "command": "apply_motion",
            "params": {
                "name": "wave",
                "params": sanitized
            }
        }

    elif canonical_name == "apply_motion_idle":
        # duration_s
        duration_s = arguments.get("duration_s")
        if duration_s is None:
            duration_s = defaults["duration_s"]
            applied_defaults["duration_s"] = duration_s
        else:
            try:
                duration_s = float(duration_s)
                if duration_s < 0.3:
                    errors.append(f"duration_s must be at least 0.3s (got {duration_s}s).")
            except (ValueError, TypeError):
                errors.append(f"duration_s must be numeric.")
        sanitized["duration_s"] = duration_s

        # fps
        fps = arguments.get("fps")
        if fps is None:
            fps = defaults["fps"]
            applied_defaults["fps"] = fps
        else:
            try:
                fps = int(fps)
                if fps < 1:
                    errors.append(f"fps must be at least 1 (got {fps}).")
            except (ValueError, TypeError):
                errors.append(f"fps must be an integer.")
        sanitized["fps"] = fps

        bridge_cmd = {
            "command": "apply_motion",
            "params": {
                "name": "idle",
                "params": sanitized
            }
        }

    elif canonical_name == "set_frame_range":
        start = arguments.get("start")
        if start is None:
            start = defaults["start"]
            applied_defaults["start"] = start
        else:
            try:
                start = int(start)
                if start < 1:
                    errors.append(f"start frame must be >= 1 (got {start}).")
            except (ValueError, TypeError):
                errors.append(f"start frame must be an integer.")
        sanitized["start"] = start

        end = arguments.get("end")
        if end is None:
            end = defaults["end"]
            applied_defaults["end"] = end
        else:
            try:
                end = int(end)
                if end < 1:
                    errors.append(f"end frame must be >= 1 (got {end}).")
            except (ValueError, TypeError):
                errors.append(f"end frame must be an integer.")
        sanitized["end"] = end

        if not errors and start > end:
            errors.append(f"Start frame ({start}) cannot be greater than end frame ({end}).")

        bridge_cmd = {
            "command": "set_frame_range",
            "params": sanitized
        }
    else:
        errors.append(f"Unhandled canonical tool '{canonical_name}'.")
        bridge_cmd = None

    if errors:
        return ValidationResult(
            valid=False,
            tool_name=tool_name,
            canonical_tool=canonical_name,
            errors=errors,
            message="; ".join(errors)
        )

    # Success message with defaults notice if any applied
    defaults_info = ""
    if applied_defaults:
        defaults_info = f" (Applied defaults: {applied_defaults})"

    return ValidationResult(
        valid=True,
        tool_name=tool_name,
        canonical_tool=canonical_name,
        sanitized_args=sanitized,
        applied_defaults=applied_defaults,
        bridge_command=bridge_cmd,
        message=f"Validated '{tool_name}' successfully{defaults_info}."
    )
