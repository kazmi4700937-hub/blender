"""
Natural-language agent execution runner.
Translates user natural language instructions into tool calls (via Anthropic Claude VLM/LLM
or deterministic offline fallback), validates parameters, executes them via the Blender bridge,
and generates preview renders.
"""

import os
import re
import yaml
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from .tools import TOOLS, AVAILABLE_MOTIONS
from .validator import validate_tool_call, ValidationResult, format_unknown_tool_message
from ..bridge_client import BridgeClient, BridgeError
from ..settings import load_config, get_model_name, get_api_key

@dataclass
class AgentExecutionResult:
    success: bool
    message: str
    tool_calls: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    validated_results: List[ValidationResult] = field(default_factory=list)
    bridge_commands: List[Dict[str, Any]] = field(default_factory=list)
    applied_defaults: List[Dict[str, Any]] = field(default_factory=list)
    preview_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)


def offline_parse_user_intent(user_text: str) -> Tuple[List[Tuple[str, Dict[str, Any]]], str]:
    """
    Deterministic rule-based parser used when ANTHROPIC_API_KEY is not available
    or for fast local unit testing.
    """
    text_lower = user_text.lower().strip()

    # 1. Unsupported motion rejection
    unsupported_keywords = [
        "dance", "tango", "salsa", "waltz", "swim", "fly", "flight",
        "backflip", "flip", "somersault", "run", "sprint", "punch",
        "kick", "sit", "climb", "crawl", "spin"
    ]
    for kw in unsupported_keywords:
        if kw in text_lower:
            return [], format_unknown_tool_message(kw)

    # 2. Jump intent
    if "jump" in text_lower or "leap" in text_lower:
        # Check if platform or high ground is mentioned
        is_high_ground = any(k in text_lower for k in ["high ground", "platform", "ledge", "height", "high"])
        
        # Extract height if specified (e.g. "3 meter", "3m", "3.5 meters", "height of 3")
        height_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters)?\s*(?:high|height|platform)', text_lower)
        if not height_match:
            height_match = re.search(r'from\s+(?:a\s+)?(\d+(?:\.\d+)?)\s*(?:m|meter|meters)?', text_lower)
        if not height_match:
            height_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters)', text_lower)

        tool_calls: List[Tuple[str, Dict[str, Any]]] = []
        if is_high_ground or (height_match and float(height_match.group(1)) > 0.0):
            height_val = float(height_match.group(1)) if height_match else 2.0
            tool_calls.append(("build_environment", {"kind": "platform_drop", "height_m": height_val}))
            tool_calls.append(("apply_motion_jump", {"start_height_m": height_val}))
            msg = f"Planning jump motion from {height_val}m platform."
        else:
            # Ambiguous jump or flat ground jump: leave args empty so validator applies all defaults
            tool_calls.append(("apply_motion_jump", {}))
            msg = "Planning jump motion (using default parameters)."

        return tool_calls, msg

    # 3. Walk intent
    if "walk" in text_lower:
        dist_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters)', text_lower)
        dist_val = float(dist_match.group(1)) if dist_match else 2.0
        return [("apply_motion_walk", {"distance_m": dist_val})], f"Planning walk motion ({dist_val}m)."

    # 4. Wave intent
    if "wave" in text_lower or "greet" in text_lower or "hello" in text_lower:
        return [("apply_motion_wave", {})], "Planning wave motion."

    # 5. Idle intent
    if "idle" in text_lower or "breathe" in text_lower or "stand" in text_lower or "rest" in text_lower:
        return [("apply_motion_idle", {})], "Planning idle breathing motion."

    # Unrecognized intent
    return [], format_unknown_tool_message(user_text)


def parse_user_intent_llm(user_text: str, model_name: str, api_key: str) -> Tuple[List[Tuple[str, Dict[str, Any]]], str]:
    """
    Parses user command using Anthropic Claude API with tool use.
    """
    import anthropic

    system_prompt = (
        "You are an assistant controlling a 3D humanoid character in Blender.\n"
        "Your task is to translate the user's natural language command into the appropriate tool calls.\n\n"
        "Available tools:\n"
        "- build_environment: creates a ground plane and optional elevated platform. "
        "If the user asks to jump from high ground or a platform of height H meters, you MUST call "
        "build_environment(kind='platform_drop', height_m=H) FIRST, followed by apply_motion_jump(start_height_m=H).\n"
        "- apply_motion_jump: jump animation with flight trajectory.\n"
        "- apply_motion_walk: walking animation.\n"
        "- apply_motion_wave: waving hand animation.\n"
        "- apply_motion_idle: idle breathing animation.\n"
        "- set_frame_range: configure scene frame range.\n\n"
        "STRICT SAFETY & SCOPE RULES:\n"
        "1. If the user asks for a motion outside the available set (such as dancing, tango, swimming, flying, backflips), "
        "DO NOT invent a tool or call an invalid tool. Instead, respond politely with plain text explaining that only "
        "idle, wave, jump, and walk motions are supported.\n"
        "2. Do not emit raw python or bpy code.\n"
        "3. Use appropriate parameter defaults if values are not specified by the user.\n"
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_name,
        max_tokens=1024,
        system=system_prompt,
        tools=TOOLS,
        messages=[{"role": "user", "content": user_text}]
    )

    tool_calls: List[Tuple[str, Dict[str, Any]]] = []
    text_responses: List[str] = []

    for block in response.content:
        if block.type == "tool_use":
            tool_calls.append((block.name, block.input))
        elif block.type == "text":
            text_responses.append(block.text)

    msg = "\n".join(text_responses) if text_responses else "Tool calls planned."
    return tool_calls, msg


def run_agent_command(
    user_text: str,
    bridge_client: Optional[BridgeClient] = None,
    render_preview: bool = True,
    preview_output_path: str = "output/previews/agent_preview.png"
) -> AgentExecutionResult:
    """
    End-to-end execution of a user command:
    1. Parse text -> tool calls (Claude LLM or offline fallback)
    2. Validate tool calls and parameters
    3. If valid and bridge_client available, execute bridge commands in Blender
    4. Render preview image if requested
    """
    cfg = load_config()
    model_name = get_model_name(cfg)
    api_key = get_api_key(cfg)

    # 1. Parse user intent
    if api_key:
        try:
            tool_calls, llm_msg = parse_user_intent_llm(user_text, model_name=model_name, api_key=api_key)
        except Exception as e:
            # Fallback to offline parser if API call fails
            tool_calls, llm_msg = offline_parse_user_intent(user_text)
    else:
        tool_calls, llm_msg = offline_parse_user_intent(user_text)

    # If no tool calls were produced (e.g. polite rejection of unsupported request or informational query)
    if not tool_calls:
        return AgentExecutionResult(
            success=True,
            message=llm_msg,
            tool_calls=[],
            validated_results=[],
            bridge_commands=[],
            applied_defaults=[],
            preview_path=None
        )

    # 2. Validate all proposed tool calls
    validated_results: List[ValidationResult] = []
    bridge_commands: List[Dict[str, Any]] = []
    all_defaults: List[Dict[str, Any]] = []
    validation_errors: List[str] = []

    for tool_name, tool_args in tool_calls:
        v_res = validate_tool_call(tool_name, tool_args)
        validated_results.append(v_res)
        if not v_res.valid:
            validation_errors.extend(v_res.errors)
        else:
            if v_res.bridge_command:
                bridge_commands.append(v_res.bridge_command)
            if v_res.applied_defaults:
                all_defaults.append({
                    "tool": tool_name,
                    "defaults": v_res.applied_defaults
                })

    # If any tool call was invalid, abort immediately before sending anything to Blender
    if validation_errors:
        err_msg = "Validation failed: " + "; ".join(validation_errors)
        return AgentExecutionResult(
            success=False,
            message=err_msg,
            tool_calls=tool_calls,
            validated_results=validated_results,
            bridge_commands=[],
            applied_defaults=all_defaults,
            errors=validation_errors
        )

    # 3. Execute bridge commands in Blender if bridge_client provided
    executed_preview_path = None
    if bridge_client:
        try:
            for cmd in bridge_commands:
                bridge_client.send_command(cmd["command"], cmd.get("params", {}))

            if render_preview:
                os.makedirs(os.path.dirname(os.path.abspath(preview_output_path)), exist_ok=True)
                # Frame to preview: middle or landing frame if known
                res = bridge_client.render_preview(path=preview_output_path)
                executed_preview_path = res.get("path", preview_output_path)
        except BridgeError as be:
            return AgentExecutionResult(
                success=False,
                message=f"Blender bridge execution error: {be}",
                tool_calls=tool_calls,
                validated_results=validated_results,
                bridge_commands=bridge_commands,
                applied_defaults=all_defaults,
                errors=[str(be)]
            )

    # Build comprehensive success message
    defaults_summary = ""
    if all_defaults:
        defaults_strs = [f"{d['tool']} -> {d['defaults']}" for d in all_defaults]
        defaults_summary = f" [Applied defaults: {'; '.join(defaults_strs)}]"

    summary_msg = f"Executed {len(bridge_commands)} command(s) successfully.{defaults_summary}"

    return AgentExecutionResult(
        success=True,
        message=summary_msg,
        tool_calls=tool_calls,
        validated_results=validated_results,
        bridge_commands=bridge_commands,
        applied_defaults=all_defaults,
        preview_path=executed_preview_path
    )
