"""Strict-harness budget configuration and accounting primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
import posixpath
import re
import shlex
from time import monotonic
from typing import Any, Mapping
import tomllib


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    """Immutable hard limits for one benchmark attempt.

    The defaults are the Core-GOD limits from the redesign specification. They
    also let tasks without a contract continue to run under finite limits.
    """

    max_agent_turns: int = 24
    max_weighted_tool_cost: int = 44
    max_public_test_runs: int = 3
    max_file_read_bytes: int = 180_000
    wall_clock_seconds: int = 900
    max_model_tokens: int = 64_000

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{item.name} must be an integer")
            if value <= 0:
                raise ValueError(f"{item.name} must be greater than zero")

    def as_dict(self) -> dict[str, int]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True, slots=True)
class TaskConfig:
    """Strict task entry points and trusted commands."""

    id: str = ""
    entry: str = "/app/files"
    public_test: str = "python3 -m pytest -q /app/files/tests.py"
    build: str | None = None
    outputs: tuple[str, ...] = ()

    @property
    def output(self) -> tuple[str, ...]:
        return self.outputs


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Policy fields enforced by the mediated strict tools."""

    editable: tuple[str, ...] = ()
    network: bool = False
    forbid_imports: tuple[str, ...] = ()
    determinism: bool = True

    @property
    def require_determinism(self) -> bool:
        return self.determinism


@dataclass(frozen=True, slots=True)
class ContextConfig:
    """Optional generic retrieval-ground-truth configuration."""

    authoritative_spec: str | None = None
    relevant_paths: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.authoritative_spec is not None or bool(self.relevant_paths)

    @property
    def patterns(self) -> tuple[str, ...]:
        if self.authoritative_spec is None:
            return self.relevant_paths
        return tuple(dict.fromkeys((self.authoritative_spec, *self.relevant_paths)))


@dataclass(frozen=True, slots=True)
class TaskContract:
    """Typed strict-harness view of ``files/contract.toml``."""

    task: TaskConfig
    policy: PolicyConfig
    budget: BudgetConfig
    output: Mapping[str, Any] = field(default_factory=dict)
    context: ContextConfig = field(default_factory=ContextConfig)

    @property
    def entry(self) -> str:
        return self.task.entry

    @property
    def public_test(self) -> str:
        return self.task.public_test

    @property
    def build(self) -> str | None:
        return self.task.build

    @property
    def outputs(self) -> tuple[str, ...]:
        return self.task.outputs

    @property
    def editable(self) -> tuple[str, ...]:
        return self.policy.editable

    @property
    def limits(self) -> BudgetConfig:
        return self.budget


def _table(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"contract [{name}] must be a TOML table")
    return value


def _string(value: Any, name: str, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} contains an unsafe control character")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be an array of strings")
    result = tuple(value)
    if any(not item or "\x00" in item or "\n" in item or "\r" in item for item in result):
        raise ValueError(f"{name} contains an empty or unsafe value")
    return result


def _app_files_path(path: str, name: str) -> str:
    if not path.startswith("/"):
        path = f"/app/files/{path}"
    normalized = posixpath.normpath(path)
    if normalized != "/app/files" and not normalized.startswith("/app/files/"):
        raise ValueError(f"{name} must be under /app/files")
    return normalized


def _editable_pattern(pattern: str) -> str:
    if pattern.startswith("/") or "\\" in pattern:
        raise ValueError("policy.editable patterns must be relative to /app/files")
    normalized = posixpath.normpath(pattern)
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ValueError("policy.editable contains an unsafe path pattern")
    if not re.fullmatch(r"[A-Za-z0-9_./*?\[\]-]+", normalized):
        raise ValueError("policy.editable contains unsafe pattern characters")
    return normalized


def parse_public_test_argv(command: str) -> tuple[str, ...]:
    """Parse the trusted public pytest command without invoking a shell."""

    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError as error:
        raise ValueError("task.public_test has invalid quoting") from error
    if not argv or any(token in {"|", "||", "&", "&&", ";", "<", ">"} for token in argv):
        raise ValueError("task.public_test must be a single argv-style command")
    if argv[0] not in {"python", "python3", "pytest", "py.test", "/app/.venv/bin/python"}:
        raise ValueError("task.public_test must invoke pytest")
    executable = posixpath.basename(argv[0])
    if executable in {"python", "python3"} and not (
        len(argv) >= 3 and argv[1:3] == ("-m", "pytest")
    ):
        raise ValueError("task.public_test Python command must invoke -m pytest")
    arguments = argv[3:] if executable in {"python", "python3"} else argv[1:]
    allowed_exact = {
        "-q", "--quiet", "-v", "-vv", "-x", "--exitfirst", "--disable-warnings",
        "--strict-markers", "--strict-config",
    }
    allowed_patterns = (
        re.compile(r"--tb=(?:auto|long|short|line|native|no)$"),
        re.compile(r"--maxfail=[1-9][0-9]*$"),
        re.compile(r"-r[A-Za-z]+$"),
    )
    paths: list[str] = []
    for argument in arguments:
        if argument.startswith("-"):
            if argument not in allowed_exact and not any(
                pattern.fullmatch(argument) for pattern in allowed_patterns
            ):
                raise ValueError(f"task.public_test contains unsupported pytest option: {argument}")
            continue
        if "::" in argument:
            raise ValueError("task.public_test cannot select individual test nodes")
        paths.append(_app_files_path(argument, "task.public_test path"))
    if len(paths) != 1 or paths[0] == "/app/files":
        raise ValueError("task.public_test must name exactly one test file under /app/files")
    return argv


def load_task_contract(
    challenge_dir: str | Path,
    *,
    strict: bool = True,
    editable_fallback: list[str] | tuple[str, ...] | None = None,
) -> TaskContract:
    """Load and validate the complete strict task contract.

    Missing contracts and omitted fields receive finite, network-disabled defaults.
    A present malformed contract is rejected rather than silently weakening policy.
    """

    challenge_path = Path(challenge_dir)
    contract_path = challenge_path / "files" / "contract.toml"
    raw: dict[str, Any] = {}
    if contract_path.is_file():
        with contract_path.open("rb") as contract_file:
            loaded = tomllib.load(contract_file)
        if not isinstance(loaded, dict):
            raise TypeError("contract must contain a TOML table")
        raw = loaded

    task_raw = _table(raw.get("task"), "task")
    policy_raw = _table(raw.get("policy"), "policy")
    limits_raw = _table(raw.get("limits"), "limits")
    output_raw = _table(raw.get("output"), "output")
    context_raw = _table(raw.get("context"), "context")

    known_limits = {item.name for item in fields(BudgetConfig)}
    unknown_limits = set(limits_raw) - known_limits
    known_policy = {"editable", "network", "forbid_imports", "require_determinism"}
    unknown_policy = set(policy_raw) - known_policy
    if strict and unknown_limits:
        raise ValueError(f"unknown generic [limits] keys: {', '.join(sorted(unknown_limits))}")
    if strict and unknown_policy:
        raise ValueError(f"unknown generic [policy] keys: {', '.join(sorted(unknown_policy))}")
    budget = BudgetConfig(**{key: value for key, value in limits_raw.items() if key in known_limits})

    entry = _app_files_path(
        _string(task_raw.get("entry"), "task.entry", default="/app/files"),
        "task.entry",
    )
    public_test = _string(
        task_raw.get("public_test"),
        "task.public_test",
        default="python3 -m pytest -q /app/files/tests.py",
    )
    build_value = task_raw.get("build")
    build = None if build_value is None else _string(build_value, "task.build")
    if build == "":
        build = None
    outputs_value = task_raw.get("outputs", task_raw.get("output"))
    if isinstance(outputs_value, str):
        outputs_value = [outputs_value]
    outputs = tuple(
        _app_files_path(path, "task.outputs")
        for path in _string_tuple(outputs_value, "task.outputs")
    )

    network = policy_raw.get("network", False)
    if not isinstance(network, bool):
        raise TypeError("policy.network must be a boolean")
    if strict and network:
        raise ValueError("strict contracts cannot enable network access")
    determinism_value = policy_raw.get(
        "require_determinism", policy_raw.get("determinism", True)
    )
    if not isinstance(determinism_value, bool):
        raise TypeError("policy.require_determinism must be a boolean")
    if strict and not determinism_value:
        raise ValueError("strict contracts must require deterministic behavior")

    editable = tuple(
        _editable_pattern(pattern)
        for pattern in _string_tuple(policy_raw.get("editable"), "policy.editable")
    )
    if not editable and editable_fallback:
        editable = tuple(_editable_pattern(pattern) for pattern in editable_fallback)
    forbid_imports = _string_tuple(
        policy_raw.get("forbid_imports"), "policy.forbid_imports"
    )
    if strict:
        parse_public_test_argv(public_test)

    authoritative_value = context_raw.get("authoritative_spec")
    authoritative_spec = (
        None
        if authoritative_value is None
        else _editable_pattern(
            _string(authoritative_value, "context.authoritative_spec")
        )
    )
    if "relevant_paths" in context_raw and "relevant_path_patterns" in context_raw:
        raise ValueError(
            "[context] cannot define both relevant_paths and relevant_path_patterns"
        )
    relevant_value = context_raw.get(
        "relevant_paths", context_raw.get("relevant_path_patterns")
    )
    relevant_paths = tuple(
        _editable_pattern(pattern)
        for pattern in _string_tuple(
            relevant_value, "context.relevant_paths"
        )
    )

    return TaskContract(
        task=TaskConfig(
            id=_string(task_raw.get("id"), "task.id", default=challenge_path.name),
            entry=entry,
            public_test=public_test,
            build=build,
            outputs=outputs,
        ),
        policy=PolicyConfig(
            editable=editable,
            network=network,
            forbid_imports=forbid_imports,
            determinism=determinism_value,
        ),
        budget=budget,
        output=dict(output_raw),
        context=ContextConfig(
            authoritative_spec=authoritative_spec,
            relevant_paths=relevant_paths,
        ),
    )


def load_contract(challenge_dir: str | Path) -> BudgetConfig:
    """Load ``files/contract.toml`` limits, falling back to strict defaults."""

    contract_path = Path(challenge_dir) / "files" / "contract.toml"
    if not contract_path.is_file():
        return BudgetConfig()

    with contract_path.open("rb") as contract_file:
        contract = tomllib.load(contract_file)

    limits = contract.get("limits", {})
    if not isinstance(limits, dict):
        raise TypeError("contract [limits] must be a TOML table")

    known_limits = {item.name for item in fields(BudgetConfig)}
    configured = {key: value for key, value in limits.items() if key in known_limits}
    return BudgetConfig(**configured)


@dataclass(slots=True)
class BudgetState:
    """Mutable usage counters for a single attempt."""

    config: BudgetConfig = field(default_factory=BudgetConfig)
    turns: int = 0
    weighted_tool_cost: int = 0
    public_test_runs: int = 0
    file_read_bytes: int = 0
    no_progress_retries: int = 0
    model_tokens: int = 0
    started_at: float = field(default_factory=monotonic)
    _frozen_elapsed: float | None = field(default=None, repr=False)
    _emitted_checkpoints: set[int] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self._validate_counters()

    def _validate_counters(self) -> None:
        for name in (
            "turns",
            "weighted_tool_cost",
            "public_test_runs",
            "file_read_bytes",
            "no_progress_retries",
            "model_tokens",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

    def apply(
        self,
        *,
        turns: int = 0,
        weighted_tool_cost: int = 0,
        public_test_runs: int = 0,
        file_read_bytes: int = 0,
        no_progress_retries: int = 0,
        model_tokens: int = 0,
    ) -> None:
        """Add non-negative usage deltas to the state."""

        deltas = {
            "turns": turns,
            "weighted_tool_cost": weighted_tool_cost,
            "public_test_runs": public_test_runs,
            "file_read_bytes": file_read_bytes,
            "no_progress_retries": no_progress_retries,
            "model_tokens": model_tokens,
        }
        for name, value in deltas.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} delta must be an integer")
            if value < 0:
                raise ValueError(f"{name} delta cannot be negative")
        for name, value in deltas.items():
            setattr(self, name, getattr(self, name) + value)

    def elapsed(self, now: float | None = None) -> float:
        """Return non-negative elapsed monotonic time in seconds."""

        if self._frozen_elapsed is not None:
            return self._frozen_elapsed
        current = monotonic() if now is None else now
        return max(0.0, current - self.started_at)

    def freeze_elapsed(self, now: float | None = None) -> float:
        """Stop wall-clock accounting before verifier-only work starts."""

        if self._frozen_elapsed is None:
            current = monotonic() if now is None else now
            self._frozen_elapsed = max(0.0, current - self.started_at)
        return self._frozen_elapsed

    def utilization(self, now: float | None = None) -> float:
        """Return the largest fraction consumed among all hard limits."""

        limits = self.config
        return max(
            self.turns / limits.max_agent_turns,
            self.weighted_tool_cost / limits.max_weighted_tool_cost,
            self.public_test_runs / limits.max_public_test_runs,
            self.file_read_bytes / limits.max_file_read_bytes,
            self.model_tokens / limits.max_model_tokens,
            self.elapsed(now) / limits.wall_clock_seconds,
        )

    def checkpoint(self, now: float | None = None) -> int | None:
        """Claim the highest newly crossed checkpoint, expressed as a percent."""

        utilization = self.utilization(now)
        crossed = [
            threshold
            for threshold in (50, 80)
            if utilization >= threshold / 100 and threshold not in self._emitted_checkpoints
        ]
        if not crossed:
            return None
        self._emitted_checkpoints.update(crossed)
        return max(crossed)

    @property
    def in_finalization_mode(self) -> bool:
        return self.utilization() >= 0.8 and not self.exhausted()

    def exhausted(self, now: float | None = None) -> bool:
        limits = self.config
        return (
            self.turns >= limits.max_agent_turns
            or self.weighted_tool_cost >= limits.max_weighted_tool_cost
            or self.public_test_runs >= limits.max_public_test_runs
            or self.file_read_bytes >= limits.max_file_read_bytes
            or self.model_tokens >= limits.max_model_tokens
            or self.elapsed(now) >= limits.wall_clock_seconds
        )

    def permits(
        self,
        *,
        turns: int = 0,
        weighted_tool_cost: int = 0,
        public_test_runs: int = 0,
        file_read_bytes: int = 0,
        model_tokens: int = 0,
        now: float | None = None,
    ) -> bool:
        """Return whether prospective usage stays at or below every hard ceiling."""

        limits = self.config
        current = monotonic() if now is None else now
        return (
            self.turns + turns <= limits.max_agent_turns
            and self.weighted_tool_cost + weighted_tool_cost <= limits.max_weighted_tool_cost
            and self.public_test_runs + public_test_runs <= limits.max_public_test_runs
            and self.file_read_bytes + file_read_bytes <= limits.max_file_read_bytes
            and self.model_tokens + model_tokens <= limits.max_model_tokens
            and self.elapsed(current) <= limits.wall_clock_seconds
        )

    def within_budget(self, now: float | None = None) -> bool:
        """Return whether recorded usage has not exceeded a configured limit."""

        return self.permits(now=now)

    def as_dict(self, now: float | None = None) -> dict[str, Any]:
        """Return a JSON-compatible snapshot of limits and current usage."""

        current = monotonic() if now is None else now
        return {
            **self.config.as_dict(),
            "turns": self.turns,
            "weighted_tool_cost": self.weighted_tool_cost,
            "public_test_runs": self.public_test_runs,
            "file_read_bytes": self.file_read_bytes,
            "no_progress_retries": self.no_progress_retries,
            "model_tokens": self.model_tokens,
            "elapsed_seconds": self.elapsed(current),
            "utilization": self.utilization(current),
            "in_finalization_mode": self.utilization(current) >= 0.8
            and not self.exhausted(current),
            "exhausted": self.exhausted(current),
            "checkpoints_emitted": sorted(self._emitted_checkpoints),
        }
