from __future__ import annotations

from harbor.models.agent.context import AgentContext

from common.harbor_cli_agents import GodBenchOpenCode, GodBenchPi


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
