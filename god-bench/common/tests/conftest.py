from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from types import ModuleType


COMMON_DIR = Path(__file__).resolve().parents[1]
GOD_BENCH_DIR = COMMON_DIR.parent
sys.path.insert(0, str(GOD_BENCH_DIR))
sys.path.insert(0, str(COMMON_DIR))


def _module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules[name] = module
    return module


try:
    import harbor  # noqa: F401
except ImportError:
    for name in (
        "harbor",
        "harbor.agents",
        "harbor.environments",
        "harbor.models",
        "harbor.models.agent",
        "harbor.models.task",
        "harbor.models.verifier",
        "harbor.verifier",
    ):
        _module(name)

    class BaseAgent:
        def __init__(self, logs_dir, model_name=None, logger=None, **kwargs):
            self.logs_dir = logs_dir
            self.model_name = model_name
            self.logger = logger

    class BaseEnvironment:
        pass

    class AgentContext:
        pass

    class NetworkMode(str, Enum):
        NO_NETWORK = "no-network"
        PUBLIC = "public"

    class VerifierResult:
        def __init__(self, rewards=None):
            self.rewards = rewards

    class BaseVerifier:
        def __init__(
            self, *, task, trial_paths, environment, override_env=None,
            logger=None, verifier_env=None, step_name=None, **kwargs
        ):
            self.task = task
            self.trial_paths = trial_paths
            self.environment = environment
            self.override_env = override_env or {}
            self.logger = logger or type(
                "Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None)}
            )()
            self.verifier_env = verifier_env
            self.step_name = step_name

    modules = {
        "harbor.agents.base": {"BaseAgent": BaseAgent},
        "harbor.environments.base": {"BaseEnvironment": BaseEnvironment},
        "harbor.models.agent.context": {"AgentContext": AgentContext},
        "harbor.models.task.config": {"NetworkMode": NetworkMode},
        "harbor.models.verifier.result": {"VerifierResult": VerifierResult},
        "harbor.verifier.base": {"BaseVerifier": BaseVerifier},
    }
    for name, values in modules.items():
        module = _module(name)
        for key, value in values.items():
            setattr(module, key, value)
