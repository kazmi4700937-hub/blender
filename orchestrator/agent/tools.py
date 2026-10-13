"""
Tool definitions and JSON schemas for LLM-driven animation and environment creation.
Follows Anthropic Claude tool calling specifications.
"""

from typing import Dict, Any, List

# Supported motions
AVAILABLE_MOTIONS = ["idle", "wave", "jump", "walk"]

# Tool JSON schemas for Claude API
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "build_environment",
        "description": (
            "Creates a 3D environment for the character in Blender. "
            "For a jump or drop from elevated ground or platform, set kind='platform_drop' and specify height_m. "
            "For standard flat ground, set kind='ground'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["ground", "platform_drop"],
                    "description": "Environment type: 'ground' for flat ground, 'platform_drop' for an elevated platform with ground plane. Default: 'ground'."
                },
                "height_m": {
                    "type": "number",
                    "minimum": 0.0,
                    "description": "Platform height in meters (must be >= 0.0). Required for platform_drop. Default: 2.0."
                },
                "size_m": {
                    "type": "number",
                    "exclusiveMinimum": 0.0,
                    "description": "Overall ground plane dimension in meters (must be > 0.0). Default: 10.0."
                }
            },
            "required": []
        }
    },
    {
        "name": "apply_motion_jump",
        "description": (
            "Applies a jump animation to the character with preparation crouch, ballistic flight, and landing absorption. "
            "If jumping down from an elevated platform or high ground, set start_height_m to the platform height and end_height_m to 0.0. "
            "For jumping on flat ground, start_height_m and end_height_m should be 0.0."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_height_m": {
                    "type": "number",
                    "minimum": 0.0,
                    "description": "Elevation where the jump starts in meters (must be >= 0.0). Default: 0.0."
                },
                "end_height_m": {
                    "type": "number",
                    "minimum": 0.0,
                    "description": "Elevation where the character lands in meters (must be >= 0.0). Default: 0.0."
                },
                "forward_distance_m": {
                    "type": "number",
                    "description": "Horizontal forward leap distance in meters. Default: 1.5."
                },
                "duration_s": {
                    "type": "number",
                    "minimum": 0.3,
                    "description": "Total duration of jump animation in seconds (must be >= 0.3s). Default: 1.2."
                },
                "fps": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Animation frames per second. Default: 24."
                }
            },
            "required": []
        }
    },
    {
        "name": "apply_motion_walk",
        "description": "Applies a forward walking gait cycle animation with alternating foot steps and torso movement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "distance_m": {
                    "type": "number",
                    "minimum": 0.0,
                    "description": "Distance to walk forward in meters (must be >= 0.0). Default: 2.0."
                },
                "duration_s": {
                    "type": "number",
                    "minimum": 0.3,
                    "description": "Total duration of walk cycle in seconds (must be >= 0.3s). Default: 2.0."
                },
                "fps": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Animation frames per second. Default: 24."
                }
            },
            "required": []
        }
    },
    {
        "name": "apply_motion_wave",
        "description": "Applies a friendly hand wave animation using the character's right arm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_s": {
                    "type": "number",
                    "minimum": 0.3,
                    "description": "Duration of the wave animation in seconds (must be >= 0.3s). Default: 2.0."
                },
                "fps": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Animation frames per second. Default: 24."
                }
            },
            "required": []
        }
    },
    {
        "name": "apply_motion_idle",
        "description": "Applies a gentle idle breathing animation loop.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_s": {
                    "type": "number",
                    "minimum": 0.3,
                    "description": "Duration of the idle loop in seconds (must be >= 0.3s). Default: 2.0."
                },
                "fps": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Animation frames per second. Default: 24."
                }
            },
            "required": []
        }
    },
    {
        "name": "set_frame_range",
        "description": "Sets the scene playback frame range (start frame and end frame).",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Start frame (must be >= 1 and <= end). Default: 1."
                },
                "end": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "End frame (must be >= start). Default: 48."
                }
            },
            "required": ["start", "end"]
        }
    }
]

# Canonical tool parameter defaults
TOOL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "build_environment": {
        "kind": "ground",
        "height_m": 2.0,
        "size_m": 10.0,
    },
    "apply_motion_jump": {
        "start_height_m": 0.0,
        "end_height_m": 0.0,
        "forward_distance_m": 1.5,
        "duration_s": 1.2,
        "fps": 24,
    },
    "apply_motion_walk": {
        "distance_m": 2.0,
        "duration_s": 2.0,
        "fps": 24,
    },
    "apply_motion_wave": {
        "duration_s": 2.0,
        "fps": 24,
    },
    "apply_motion_idle": {
        "duration_s": 2.0,
        "fps": 24,
    },
    "set_frame_range": {
        "start": 1,
        "end": 48,
    },
}

# Alias mapping for convenient tool name normalization
TOOL_ALIASES: Dict[str, str] = {
    "jump": "apply_motion_jump",
    "walk": "apply_motion_walk",
    "wave": "apply_motion_wave",
    "idle": "apply_motion_idle",
}
