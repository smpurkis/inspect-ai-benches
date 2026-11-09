from __future__ import annotations

from harbor.models.agent.context import AgentContext

from common.harbor_cli_agents import GodBenchOpenCode, GodBenchPi, _pi_usage_artifact
from common.budget import BudgetConfig


def test_pi_recovers_usage_from_truncated_utf8_log(tmp_path):
    agent = GodBenchPi(logs_dir=tmp_path, model_name="openai/test-model")
    (tmp_path / "pi.txt").write_bytes(
        b'{"type":"message_end","message":{"role":"assistant","usage":'
        b'{"input":10,"output":3,"cacheRead":7,"cost":{"total":0}}}}\n'
        b'{"type":"message_end","message":{"role":"assistant","content":"\xe2'
    )
    context = AgentContext()

    agent.populate_context_post_run(context)

    assert context.n_input_tokens == 17
    assert context.n_cache_tokens == 7
    assert context.n_output_tokens == 3


def test_opencode_uses_custom_compatible_provider(tmp_path):
    agent = GodBenchOpenCode(
        logs_dir=tmp_path,
        model_name="openai/test-model",
        extra_env={
            "OPENAI_BASE_URL": "http://172.17.0.1:8234/v1",
            "OPENAI_API_KEY": "test-key",
        },
    )

    provider = agent._opencode_config["provider"]["god-bench"]
    assert agent.model_name == "god-bench/test-model"
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"]["baseURL"] == "http://172.17.0.1:8234/v1"
    assert "test-model" in provider["models"]


def test_pi_builds_verifier_usage_artifact(tmp_path):
    output = tmp_path / "pi.txt"
    output.write_text(
        '\n'.join(
            [
                '{"type":"message_end","message":{"role":"assistant","stopReason":"toolUse","usage":{"input":10,"output":3,"cacheRead":7}}}',
                '{"type":"tool_execution_start","toolCallId":"one","toolName":"read","args":{"path":"/app/files/main.py"}}',
                '{"type":"tool_execution_end","toolCallId":"one","toolName":"read","result":{"content":[{"type":"text","text":"abc"}]}}',
                '{"type":"tool_execution_start","toolCallId":"two","toolName":"bash","args":{"command":"python3 -m pytest -q /app/files/tests.py"}}',
                '{"type":"tool_execution_end","toolCallId":"two","toolName":"bash","result":{"content":[{"type":"text","text":"1 passed"}]}}',
                '{"type":"tool_execution_start","toolCallId":"three","toolName":"bash","args":{"command":"cargo build --release"}}',
                '{"type":"tool_execution_end","toolCallId":"three","toolName":"bash","args":{"command":"ignored end args"},"result":{"content":[]}}',
                '{"type":"message_end","message":{"role":"assistant","stopReason":"stop","usage":{"input":5,"output":2,"cacheRead":4}}}',
            ]
        ),
        encoding="utf-8",
    )
    contract = type("Contract", (), {"budget": BudgetConfig()})()

    artifact = _pi_usage_artifact(output, contract, 2.5)

    assert artifact["provider_usage_valid"] is True
    assert artifact["trace"]["model_input_tokens"] == 26
    assert artifact["trace"]["model_output_tokens"] == 5
    assert artifact["trace"]["tool_calls"] == 3
    assert artifact["budget_snapshot"]["weighted_tool_cost"] == 9
    assert artifact["budget_snapshot"]["public_test_runs"] == 1
    assert artifact["public_test_count"] == 1
    assert artifact["budget_snapshot"]["turns"] == 2
    assert artifact["within_budget"] is True
