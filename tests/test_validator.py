"""
Unit and acceptance tests for Phase 7: Natural-language agent and tool validator.

Tests:
1. "Make the character jump from a 3 meter high ground" produces build_environment(platform_drop, height_m=3)
   followed by apply_motion(jump, start_height_m=3).
2. A request outside the tool set (e.g. "make him dance the tango") returns a polite message listing
   available motions and sends nothing to Blender.
3. Invalid parameters from the model are rejected by the validator, and the failure is reported.
4. Ambiguous requests (e.g. "make him jump" without a height) use defaults and record applied defaults.
5. All tool parameter bounds and schema definitions are strictly enforced.
"""

import pytest
from unittest.mock import MagicMock, patch

from orchestrator.agent.tools import TOOLS, TOOL_DEFAULTS, AVAILABLE_MOTIONS
from orchestrator.agent.validator import (
    validate_tool_call,
    ValidationResult,
    format_unknown_tool_message
)
from orchestrator.agent.run import (
    offline_parse_user_intent,
    run_agent_command,
    parse_user_intent_llm
)


class TestToolsDefinitions:
    def test_tools_schema_structure(self):
        assert len(TOOLS) >= 6
        names = [t["name"] for t in TOOLS]
        assert "build_environment" in names
        assert "apply_motion_jump" in names
        assert "apply_motion_walk" in names
        assert "apply_motion_wave" in names
        assert "apply_motion_idle" in names
        assert "set_frame_range" in names

        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_available_motions(self):
        assert set(AVAILABLE_MOTIONS) == {"idle", "wave", "jump", "walk"}


class TestValidatorAcceptance:
    """
    Acceptance tests specified in Phase 7 spec.
    """

    def test_acceptance_1_jump_from_3m_platform(self):
        """
        Acceptance test 1:
        'Make the character jump from a 3 meter high ground' produces
        build_environment(platform_drop, height_m=3) followed by apply_motion(jump, start_height_m=3).
        """
        prompt = "Make the character jump from a 3 meter high ground"
        res = run_agent_command(prompt, bridge_client=None, render_preview=False)

        assert res.success is True
        assert len(res.tool_calls) == 2

        # 1. build_environment
        t1_name, t1_args = res.tool_calls[0]
        assert t1_name == "build_environment"
        assert t1_args["kind"] == "platform_drop"
        assert pytest.approx(t1_args["height_m"]) == 3.0

        # 2. apply_motion_jump
        t2_name, t2_args = res.tool_calls[1]
        assert t2_name in ["apply_motion_jump", "jump"]
        assert pytest.approx(t2_args["start_height_m"]) == 3.0

        # Verify bridge commands generated
        assert len(res.bridge_commands) == 2
        cmd1 = res.bridge_commands[0]
        assert cmd1["command"] == "build_environment"
        assert cmd1["params"]["kind"] == "platform_drop"
        assert pytest.approx(cmd1["params"]["height_m"]) == 3.0

        cmd2 = res.bridge_commands[1]
        assert cmd2["command"] == "apply_motion"
        assert cmd2["params"]["name"] == "jump"
        assert pytest.approx(cmd2["params"]["params"]["start_height_m"]) == 3.0

    def test_acceptance_2_outside_tool_set_rejected_politely(self):
        """
        Acceptance test 2:
        A request outside the tool set (for example 'make him dance the tango')
        returns a polite message listing available motions, and sends nothing to Blender.
        """
        mock_bridge = MagicMock()

        prompt = "make him dance the tango"
        res = run_agent_command(prompt, bridge_client=mock_bridge, render_preview=False)

        # Successfully handled by returning polite refusal
        assert res.success is True
        assert len(res.bridge_commands) == 0
        assert len(res.tool_calls) == 0

        # Verify polite message contains available motions
        msg_lower = res.message.lower()
        assert "cannot" in msg_lower or "not supported" in msg_lower
        for m in ["idle", "wave", "jump", "walk"]:
            assert m in msg_lower

        # Crucial check: verify nothing was sent to Blender
        mock_bridge.send_command.assert_not_called()
        mock_bridge.render_preview.assert_not_called()

    def test_acceptance_3_invalid_parameters_rejected(self):
        """
        Acceptance test 3:
        Invalid parameters from the model are rejected by the validator,
        and the failure is reported.
        """
        mock_bridge = MagicMock()

        # Direct validator test with negative height
        val_res1 = validate_tool_call("apply_motion_jump", {"start_height_m": -5.0})
        assert val_res1.valid is False
        assert any("negative" in err.lower() for err in val_res1.errors)

        # Duration < 0.3s
        val_res2 = validate_tool_call("apply_motion_jump", {"duration_s": 0.1})
        assert val_res2.valid is False
        assert any("0.3" in err for err in val_res2.errors)

        # Negative platform height
        val_res3 = validate_tool_call("build_environment", {"kind": "platform_drop", "height_m": -2.0})
        assert val_res3.valid is False
        assert any("negative" in err.lower() for err in val_res3.errors)

        # Non-positive ground size
        val_res4 = validate_tool_call("build_environment", {"size_m": 0.0})
        assert val_res4.valid is False
        assert any("greater than 0" in err.lower() for err in val_res4.errors)

        # Start frame > end frame
        val_res5 = validate_tool_call("set_frame_range", {"start": 50, "end": 10})
        assert val_res5.valid is False
        assert any("greater than" in err.lower() for err in val_res5.errors)

        # Simulate LLM returning invalid tool call in run_agent_command
        with patch("orchestrator.agent.run.offline_parse_user_intent", return_value=(
            [("apply_motion_jump", {"start_height_m": -10.0})], "Planning jump"
        )):
            res = run_agent_command("jump with invalid height", bridge_client=mock_bridge)
            assert res.success is False
            assert len(res.errors) > 0
            assert "negative" in res.message.lower()
            # Verified nothing was sent to Blender
            mock_bridge.send_command.assert_not_called()

    def test_ambiguous_requests_use_defaults(self):
        """
        Spec requirement 4:
        For ambiguous requests (for example 'make him jump' without a height),
        use the defaults and tell the user which defaults were applied.
        """
        val_res = validate_tool_call("apply_motion_jump", {})
        assert val_res.valid is True
        assert val_res.applied_defaults["start_height_m"] == 0.0
        assert val_res.applied_defaults["duration_s"] == 1.2
        assert val_res.applied_defaults["fps"] == 24
        assert val_res.applied_defaults["forward_distance_m"] == 1.5

        # Check in run_agent_command
        res = run_agent_command("Make him jump", bridge_client=None, render_preview=False)
        assert res.success is True
        assert len(res.applied_defaults) > 0
        assert any("start_height_m" in d["defaults"] for d in res.applied_defaults)


class TestDirectValidatorCoverage:
    def test_unknown_tool(self):
        val_res = validate_tool_call("dance_the_tango", {})
        assert val_res.valid is False
        assert "dance_the_tango" in val_res.message
        assert "idle, wave, jump, walk" in val_res.message

    def test_apply_motion_raw_unsupported(self):
        val_res = validate_tool_call("apply_motion", {"name": "salsa", "params": {}})
        assert val_res.valid is False
        assert "salsa" in val_res.message

    def test_apply_motion_raw_supported(self):
        val_res = validate_tool_call("apply_motion", {"name": "wave", "params": {"duration_s": 3.0}})
        assert val_res.valid is True
        assert val_res.bridge_command["command"] == "apply_motion"
        assert val_res.bridge_command["params"]["name"] == "wave"
        assert val_res.bridge_command["params"]["params"]["duration_s"] == 3.0

    def test_walk_validation(self):
        val_valid = validate_tool_call("apply_motion_walk", {"distance_m": 4.0, "duration_s": 3.5})
        assert val_valid.valid is True
        assert val_valid.bridge_command["params"]["params"]["distance_m"] == 4.0

        val_invalid = validate_tool_call("apply_motion_walk", {"distance_m": -1.0})
        assert val_invalid.valid is False

    def test_set_frame_range_validation(self):
        val_valid = validate_tool_call("set_frame_range", {"start": 1, "end": 100})
        assert val_valid.valid is True
        assert val_valid.sanitized_args["start"] == 1
        assert val_valid.sanitized_args["end"] == 100

        val_invalid_order = validate_tool_call("set_frame_range", {"start": 100, "end": 1})
        assert val_invalid_order.valid is False

        val_invalid_neg = validate_tool_call("set_frame_range", {"start": -1, "end": 10})
        assert val_invalid_neg.valid is False


class TestMockLLMParsing:
    def test_parse_user_intent_llm_tool_use(self):
        mock_client_cls = MagicMock()
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        mock_block_tool1 = MagicMock()
        mock_block_tool1.type = "tool_use"
        mock_block_tool1.name = "build_environment"
        mock_block_tool1.input = {"kind": "platform_drop", "height_m": 3.0}

        mock_block_tool2 = MagicMock()
        mock_block_tool2.type = "tool_use"
        mock_block_tool2.name = "apply_motion_jump"
        mock_block_tool2.input = {"start_height_m": 3.0}

        mock_response = MagicMock()
        mock_response.content = [mock_block_tool1, mock_block_tool2]
        mock_instance.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", mock_client_cls):
            tool_calls, msg = parse_user_intent_llm(
                "Jump from 3m platform",
                model_name="test-model",
                api_key="test_api_key"
            )

            assert len(tool_calls) == 2
            assert tool_calls[0] == ("build_environment", {"kind": "platform_drop", "height_m": 3.0})
            assert tool_calls[1] == ("apply_motion_jump", {"start_height_m": 3.0})

    def test_parse_user_intent_llm_text_refusal(self):
        mock_client_cls = MagicMock()
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        mock_block_text = MagicMock()
        mock_block_text.type = "text"
        mock_block_text.text = "I cannot perform dancing. Only idle, wave, jump, and walk are available."

        mock_response = MagicMock()
        mock_response.content = [mock_block_text]
        mock_instance.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", mock_client_cls):
            tool_calls, msg = parse_user_intent_llm(
                "Dance the salsa",
                model_name="test-model",
                api_key="test_api_key"
            )

            assert len(tool_calls) == 0
            assert "Only idle, wave, jump, and walk are available" in msg
