"""Versioned usage events, traces, and efficiency scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from math import isfinite, sqrt
from typing import Any, Mapping


USAGE_SCHEMA_VERSION = 1


def _non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _non_negative_number(name: str, value: int | float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """One mediated tool action in the strict harness."""

    turn: int
    tool: str
    normalized_command: str
    action_class: str
    tool_cost: int
    input_chars: int = 0
    output_chars: int = 0
    read_bytes: int = 0
    editable_fingerprint_before: str = ""
    editable_fingerprint_after: str = ""
    no_progress: bool = False
    elapsed_seconds: float = 0.0
    duration_seconds: float = 0.0
    observed_path: str | None = None
    relevant: bool | None = None
    schema_version: int = USAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("turn", "tool_cost", "input_chars", "output_chars", "read_bytes"):
            _non_negative_int(name, getattr(self, name))
        _non_negative_number("elapsed_seconds", self.elapsed_seconds)
        _non_negative_number("duration_seconds", self.duration_seconds)
        if not isinstance(self.no_progress, bool):
            raise TypeError("no_progress must be a boolean")
        if self.observed_path is not None and not isinstance(self.observed_path, str):
            raise TypeError("observed_path must be a string or None")
        if self.relevant is not None and not isinstance(self.relevant, bool):
            raise TypeError("relevant must be a boolean or None")
        if self.relevant is not None and self.observed_path is None:
            raise ValueError("relevant requires observed_path")
        for name in ("tool", "normalized_command", "action_class"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        if self.schema_version != USAGE_SCHEMA_VERSION:
            raise ValueError(f"unsupported usage schema version: {self.schema_version}")

    def as_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "turn": self.turn,
            "tool": self.tool,
            "normalized_command": self.normalized_command,
            "class": self.action_class,
            "tool_cost": self.tool_cost,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "read_bytes": self.read_bytes,
            "editable_fingerprint_before": self.editable_fingerprint_before,
            "editable_fingerprint_after": self.editable_fingerprint_after,
            "no_progress": self.no_progress,
            "elapsed_seconds": self.elapsed_seconds,
            "duration_seconds": self.duration_seconds,
        }
        if self.observed_path is not None:
            result["observed_path"] = self.observed_path
        if self.relevant is not None:
            result["relevant"] = self.relevant
        return result

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.as_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> UsageEvent:
        return cls(
            schema_version=value.get("schema_version", USAGE_SCHEMA_VERSION),
            turn=value["turn"],
            tool=value["tool"],
            normalized_command=value.get("normalized_command", ""),
            action_class=value["class"],
            tool_cost=value["tool_cost"],
            input_chars=value.get("input_chars", 0),
            output_chars=value.get("output_chars", 0),
            read_bytes=value.get("read_bytes", 0),
            editable_fingerprint_before=value.get("editable_fingerprint_before", ""),
            editable_fingerprint_after=value.get("editable_fingerprint_after", ""),
            no_progress=value.get("no_progress", False),
            elapsed_seconds=value.get("elapsed_seconds", 0.0),
            duration_seconds=value.get("duration_seconds", 0.0),
            observed_path=value.get("observed_path"),
            relevant=value.get("relevant"),
        )

    @classmethod
    def from_json(cls, value: str) -> UsageEvent:
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError("usage event JSON must contain an object")
        return cls.from_dict(decoded)


@dataclass(slots=True)
class UsageTrace:
    """Complete provider and tool usage for one benchmark attempt."""

    events: list[UsageEvent] = field(default_factory=list)
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    benchmark_boilerplate_tokens: int = 0
    task_text_tokens: int = 0
    elapsed_seconds: float = 0.0
    diagnostic_token_estimate_method: str = "utf8_bytes_div4_ceiling"
    schema_version: int = USAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "model_input_tokens",
            "model_output_tokens",
            "benchmark_boilerplate_tokens",
            "task_text_tokens",
        ):
            _non_negative_int(name, getattr(self, name))
        _non_negative_number("elapsed_seconds", self.elapsed_seconds)
        if self.schema_version != USAGE_SCHEMA_VERSION:
            raise ValueError(f"unsupported usage schema version: {self.schema_version}")
        if not all(isinstance(event, UsageEvent) for event in self.events):
            raise TypeError("events must contain UsageEvent instances")
        if self.diagnostic_token_estimate_method != "utf8_bytes_div4_ceiling":
            raise ValueError("unsupported diagnostic token estimate method")

    @property
    def model_tokens(self) -> int:
        """Provider-billed total; tool text is intentionally not added again."""

        return self.model_input_tokens + self.model_output_tokens

    @property
    def weighted_tool_cost(self) -> int:
        return sum(event.tool_cost for event in self.events)

    @property
    def tool_output_chars(self) -> int:
        return sum(event.output_chars for event in self.events)

    @property
    def file_read_bytes(self) -> int:
        return sum(event.read_bytes for event in self.events)

    @property
    def no_progress_retries(self) -> int:
        return sum(event.no_progress for event in self.events)

    @property
    def unique_files_opened(self) -> int | None:
        if not any(event.relevant is not None for event in self.events):
            return None
        return len(
            {event.observed_path for event in self.events if event.observed_path is not None}
        )

    @property
    def relevant_files_opened(self) -> int | None:
        if self.unique_files_opened is None:
            return None
        return len(
            {
                event.observed_path
                for event in self.events
                if event.observed_path is not None and event.relevant is True
            }
        )

    @property
    def retrieval_precision(self) -> float | None:
        unique = self.unique_files_opened
        relevant = self.relevant_files_opened
        if unique is None or relevant is None:
            return None
        return relevant / unique if unique else 0.0

    def append(self, event: UsageEvent) -> None:
        if not isinstance(event, UsageEvent):
            raise TypeError("event must be a UsageEvent")
        self.events.append(event)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_input_tokens": self.model_input_tokens,
            "model_output_tokens": self.model_output_tokens,
            "model_tokens": self.model_tokens,
            "benchmark_boilerplate_tokens": self.benchmark_boilerplate_tokens,
            "task_text_tokens": self.task_text_tokens,
            "diagnostic_token_estimate_method": self.diagnostic_token_estimate_method,
            "tool_output_chars": self.tool_output_chars,
            "weighted_tool_cost": self.weighted_tool_cost,
            "tool_calls": len(self.events),
            "file_read_bytes": self.file_read_bytes,
            "no_progress_retries": self.no_progress_retries,
            "elapsed_seconds": self.elapsed_seconds,
            "unique_files_opened": self.unique_files_opened,
            "relevant_files_opened": self.relevant_files_opened,
            "retrieval_precision": self.retrieval_precision,
            "events": [event.as_dict() for event in self.events],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.as_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> UsageTrace:
        events = value.get("events", [])
        if not isinstance(events, list):
            raise TypeError("usage trace events must be a list")
        return cls(
            schema_version=value.get("schema_version", USAGE_SCHEMA_VERSION),
            events=[UsageEvent.from_dict(event) for event in events],
            model_input_tokens=value.get("model_input_tokens", 0),
            model_output_tokens=value.get("model_output_tokens", 0),
            benchmark_boilerplate_tokens=value.get("benchmark_boilerplate_tokens", 0),
            task_text_tokens=value.get("task_text_tokens", 0),
            elapsed_seconds=value.get("elapsed_seconds", 0.0),
            diagnostic_token_estimate_method=value.get(
                "diagnostic_token_estimate_method", "utf8_bytes_div4_ceiling"
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> UsageTrace:
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError("usage trace JSON must contain an object")
        return cls.from_dict(decoded)


def efficiency_score(
    *,
    functional_pass: bool,
    model_tokens: int,
    token_budget: int,
    weighted_tool_cost: int,
    tool_cost_budget: int,
    no_progress_retries: int,
    retry_allowance: int = 0,
) -> float:
    """Compute the redesign's correctness-gated continuous efficiency score."""

    for name, value in (
        ("model_tokens", model_tokens),
        ("weighted_tool_cost", weighted_tool_cost),
        ("no_progress_retries", no_progress_retries),
        ("retry_allowance", retry_allowance),
    ):
        _non_negative_int(name, value)
    for name, value in (("token_budget", token_budget), ("tool_cost_budget", tool_cost_budget)):
        _non_negative_int(name, value)
        if value == 0:
            raise ValueError(f"{name} must be greater than zero")

    if not functional_pass:
        return 0.0

    token_factor = min(1.0, sqrt(token_budget / max(model_tokens, 1)))
    tool_factor = min(1.0, sqrt(tool_cost_budget / max(weighted_tool_cost, 1)))
    retry_factor = 1.0 / (1.0 + 0.05 * max(0, no_progress_retries - retry_allowance))
    return token_factor * tool_factor * retry_factor


def summarize_usage_artifact(
    value: Mapping[str, Any] | None,
    *,
    functional_pass: bool,
) -> dict[str, Any]:
    """Validate a strict usage artifact and return fail-safe scorer metrics."""

    empty = {
        "efficiency_score": 0.0,
        "model_input_tokens": 0,
        "model_output_tokens": 0,
        "model_total_tokens": 0,
        "tool_output_chars": 0,
        "weighted_tool_cost": 0,
        "tool_calls": 0,
        "public_test_runs": 0,
        "no_progress_retries": 0,
        "file_read_bytes": 0,
        "elapsed_seconds": 0.0,
        "within_budget": False,
        "budget": {},
        "usage_valid": False,
        "unique_files_opened": None,
        "relevant_files_opened": None,
        "retrieval_precision": None,
    }
    if not isinstance(value, Mapping):
        return empty
    try:
        if value.get("schema_version") != USAGE_SCHEMA_VERSION:
            return empty
        if value.get("provider_usage_valid") is not True:
            return empty
        trace_raw = value["trace"]
        budget = value["budget"]
        snapshot = value["budget_snapshot"]
        if not isinstance(trace_raw, Mapping) or not isinstance(budget, Mapping):
            return empty
        if not isinstance(snapshot, Mapping):
            return empty
        trace = UsageTrace.from_dict(trace_raw)
        budget_names = (
            "max_agent_turns",
            "max_weighted_tool_cost",
            "max_public_test_runs",
            "max_file_read_bytes",
            "wall_clock_seconds",
            "max_model_tokens",
        )
        clean_budget = {name: budget[name] for name in budget_names}
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in clean_budget.values()
        ):
            return empty
        token_budget = clean_budget["max_model_tokens"]
        tool_budget = clean_budget["max_weighted_tool_cost"]
        counter_names = (
            "turns", "weighted_tool_cost", "public_test_runs", "file_read_bytes",
            "no_progress_retries", "model_tokens",
        )
        counters = {name: snapshot[name] for name in counter_names}
        public_runs = counters["public_test_runs"]
        for item in (token_budget, tool_budget, *counters.values()):
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                return empty
        snapshot_elapsed = snapshot["elapsed_seconds"]
        _non_negative_number("budget_snapshot.elapsed_seconds", snapshot_elapsed)
        if token_budget == 0 or tool_budget == 0:
            return empty
        if any(snapshot.get(name) != limit for name, limit in clean_budget.items()):
            return empty
        raw_aggregates = {
            "model_tokens": trace.model_tokens,
            "weighted_tool_cost": trace.weighted_tool_cost,
            "file_read_bytes": trace.file_read_bytes,
            "no_progress_retries": trace.no_progress_retries,
            "tool_calls": len(trace.events),
            "unique_files_opened": trace.unique_files_opened,
            "relevant_files_opened": trace.relevant_files_opened,
            "retrieval_precision": trace.retrieval_precision,
        }
        if any(
            name in trace_raw and trace_raw.get(name) != expected
            for name, expected in raw_aggregates.items()
        ):
            return empty
        event_public_runs = sum(
            event.action_class == "public_test" and event.tool_cost > 0
            for event in trace.events
        )
        if (
            counters["weighted_tool_cost"] != trace.weighted_tool_cost
            or counters["file_read_bytes"] != trace.file_read_bytes
            or counters["no_progress_retries"] != trace.no_progress_retries
            or counters["model_tokens"] != trace.model_tokens
            or public_runs != event_public_runs
            or value.get("public_test_count") != public_runs
            or abs(float(snapshot_elapsed) - trace.elapsed_seconds) > 1e-6
        ):
            return empty
        within_budget = (
            counters["turns"] <= clean_budget["max_agent_turns"]
            and counters["weighted_tool_cost"] <= clean_budget["max_weighted_tool_cost"]
            and public_runs <= clean_budget["max_public_test_runs"]
            and counters["file_read_bytes"] <= clean_budget["max_file_read_bytes"]
            and counters["model_tokens"] <= clean_budget["max_model_tokens"]
            and snapshot_elapsed <= clean_budget["wall_clock_seconds"]
        )
        if value.get("within_budget") is not within_budget:
            return empty
        efficiency = efficiency_score(
            functional_pass=functional_pass,
            model_tokens=trace.model_tokens,
            token_budget=token_budget,
            weighted_tool_cost=trace.weighted_tool_cost,
            tool_cost_budget=tool_budget,
            no_progress_retries=trace.no_progress_retries,
        )
    except (
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return empty

    return {
        "efficiency_score": efficiency,
        "model_input_tokens": trace.model_input_tokens,
        "model_output_tokens": trace.model_output_tokens,
        "model_total_tokens": trace.model_tokens,
        "tool_output_chars": trace.tool_output_chars,
        "weighted_tool_cost": trace.weighted_tool_cost,
        "tool_calls": len(trace.events),
        "public_test_runs": public_runs,
        "no_progress_retries": trace.no_progress_retries,
        "file_read_bytes": trace.file_read_bytes,
        "elapsed_seconds": trace.elapsed_seconds,
        "within_budget": within_budget,
        "budget": clean_budget,
        "usage_valid": True,
        "unique_files_opened": trace.unique_files_opened,
        "relevant_files_opened": trace.relevant_files_opened,
        "retrieval_precision": trace.retrieval_precision,
    }
