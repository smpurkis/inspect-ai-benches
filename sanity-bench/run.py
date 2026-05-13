"""sanity-bench: inspect-ai tasks (one per category).

~690 tasks across 17 categories — registered as separate @task functions so
inspect can address them individually:

    uv run inspect eval sanity-bench/run.py@math \
        --model openai-api/local/your-model \
        --env LOCAL_BASE_URL=http://localhost:8234/v1 \
        --env LOCAL_API_KEY=secret

Or run all of them by omitting the @suffix:

    uv run inspect eval sanity-bench/run.py --model ...

NOTE: inspect-ai's loader is AST-based — it only discovers `@task` decorators on
top-level `def`s. The per-category functions below are deliberately explicit
(not generated dynamically) so they remain discoverable.

Scoring delegates to `scoring.py` (deterministic — exact / regex / contains /
code_exec / json_schema / length / refusal / composite). See `schema.md`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import re

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from inspect_ai import Task, task  # noqa: E402
from inspect_ai.dataset import Sample  # noqa: E402
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig  # noqa: E402
from inspect_ai.scorer import (  # noqa: E402
    CORRECT,
    INCORRECT,
    PARTIAL,
    Score,
    Scorer,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState, generate  # noqa: E402
from inspect_ai.tool import tool  # noqa: E402

from scoring import score as score_response  # noqa: E402


TASKS_DIR = ROOT / "tasks"


_FILLER_PAT = re.compile(r"\[FILLER:\s*(\d+)\s+repetitions?\s+of\s+\"([^\"]+)\"\s*\]")


def _expand_fillers(prompt: str) -> str:
    """Expand [FILLER: N repetitions of \"text\"] markers inline.

    Keeps the YAML files small while generating the actual long prompts
    needed for long-context evaluation.
    """
    def _replace(m: re.Match) -> str:
        count = int(m.group(1))
        text = m.group(2)
        return text * count

    return _FILLER_PAT.sub(_replace, prompt)


# ---------------------------------------------------------------------------
# Mock API tool — multi-turn tool calling for agentic scenarios
# ---------------------------------------------------------------------------

_CALL_HISTORY: dict[str, list[dict]] = {}


_default_results: dict[str, str] = {
    "store_secret": '{"arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:DB_PASSWORD"}',
    "get_secret": '{"value": "s3cre+!", "arn": "arn:aws:secretsmanager:..."}',
    "create_policy": '{"arn": "arn:aws:iam::123456789012:policy/secret-access"}',
    "attach_to_role": '{"status": "ok", "role": "app-server"}',
    "rotate_now": '{"status": "ok", "next_rotation": "2026-06-12T00:00:00Z"}',
    "create_launch_template": '{"id": "lt-0a1b2c3d", "name": "web-template"}',
    "create_asg": '{"name": "web-asg", "arn": "arn:aws:autoscaling:..."}',
    "attach_lb": '{"status": "ok", "target_group": "web-tg"}',
    "create_scaling_policy": '{"arn": "arn:aws:autoscaling:policy/cpu-60"}',
    "simulate_load": '{"cpu_max": 0.82, "requests_handled": 15000, "p99_latency_ms": 210}',
    "create_index": '{"status": "ok", "index": "products"}',
    "bulk_index": '{"indexed": 3, "errors": 0}',
    "search": '{"hits": [{"title": "Gaming Laptop", "price": 1299}], "total": 1}',
    "update_alias": '{"status": "ok", "alias": "prod-search"}',
    "refresh_index": '{"status": "ok"}',
    "create_queue": '{"url": "https://sqs.us-east-1.amazonaws.com/123456789012/order-queue"}',
    "create_subscription": '{"arn": "arn:aws:sns:...:order-topic:order-queue"}',
    "send_msg": '{"message_id": "msg-001", "status": "ok"}',
    "receive_msg": '{"messages": [{"id": "msg-001", "body": "test order"}], "count": 1}',
    "delete_msg": '{"status": "ok"}',
    "http_get": '{"status_code": 200, "body": [{"id": 1, "amount": 50, "status": "pending"}], "headers": {"content-type": "application/json"}}',
    "validate_json": '{"valid": true, "errors": []}',
    "flatten": '{"name": "widget", "line_items_id": 1, "line_items_qty": 2}',
    "copy_to_redshift": '{"rows_loaded": 100, "table": "dw.orders"}',
    "query_redshift": '{"rows": [{"count": 100}]}',
    "create_experiment": '{"id": "exp-001", "name": "pricing-v2"}',
    "assign_variant": '{"user": "u_42", "variant": "treatment"}',
    "record_event": '{"status": "ok"}',
    "analyze": '{"winner": "treatment", "p_value": 0.003, "uplift_pct": 5.2}',
    "promote": '{"status": "ok", "winner": "treatment"}',
    "deploy_version": '{"deploy_id": "d-abc123", "service": "payment-svc", "version": "v2.1.0"}',
    "shift_traffic": '{"status": "ok", "shifted_pct": 5}',
    "monitor_errors": '{"error_rate": 0.003, "window_min": 10, "status": "healthy"}',
    "rollback": '{"status": "ok", "rolled_back_to": "v2.0.0"}',
    "full_cutover": '{"status": "ok", "version": "v2.1.0", "traffic_pct": 100}',
    "dump_db": '{"dump_file": "s3://backups/prod-public-20260513.sql.gz"}',
    "transform_schema": '{"migration_sql": "ALTER TABLE users RENAME username TO email;..."}',
    "snapshot": '{"snapshot_id": "snap-001", "status": "created"}',
    "apply_migration": '{"status": "ok", "migration": "v042"}',
    "validate_data": '{"row_count_match": true, "source_rows": 100000, "target_rows": 100000}',
    "rollback_migration": '{"status": "ok", "rolled_back_to": "v041"}',
    "create_usage_plan": '{"id": "plan-basic", "name": "basic"}',
    "create_api_key": '{"key": "abc123...", "id": "key-001"}',
    "set_throttle": '{"status": "ok"}',
    "add_waf_rule": '{"id": "waf-rate-001", "name": "rate-limit"}',
    "test_endpoint": '{"status_codes": [200, 200, 200, 429, 200], "rate_limited": 1}',
    "run_scanner": '{"scan_id": "scan-001", "profile": "prod-account"}',
    "list_findings": '{"findings": [{"id": "F-001", "severity": "CRITICAL", "title": "S3 bucket public"}], "count": 5}',
    "suppress_finding": '{"status": "ok", "finding_id": "F-001"}',
    "generate_report": '{"url": "s3://reports/scan-001.pdf"}',
    "email_report": '{"status": "ok", "sent_to": "security@co"}',
    "read_file": '{"data": "base64encoded...", "size_bytes": 102400}',
    "resize": '{"width": 1920, "height": 1080, "size_bytes": 50000}',
    "compress": '{"quality": 80, "size_bytes": 25000}',
    "store": '{"url": "https://assets-bucket.s3.amazonaws.com/photo.jpg"}',
    "generate_thumbnail": '{"url": "https://assets-bucket.s3.amazonaws.com/thumb_photo.jpg", "size": 256}',
    "create_template": '{"id": "tmpl-welcome", "name": "welcome"}',
    "send_email": '{"status": "ok", "message_id": "email-001"}',
    "send_sms": '{"status": "ok", "message_id": "sms-001"}',
    "send_slack": '{"status": "ok", "channel": "#general"}',
    "log_delivery": '{"status": "ok"}',
    "create_customer": '{"id": "cus_abc123", "email": "bob@co"}',
    "add_payment_method": '{"status": "ok", "method": "pm_abc"}',
    "create_invoice": '{"id": "inv-001", "amount": 2999, "currency": "USD"}',
    "charge": '{"status": "succeeded", "charge_id": "ch_001", "amount": 2999}',
    "refund": '{"status": "succeeded", "refund_id": "rf_001", "amount": 2999}',
    "create_ws_api": '{"id": "ws-abc123", "name": "chat-app"}',
    "deploy_ws": '{"status": "ok", "stage": "dev", "url": "wss://example.com/dev"}',
    "set_integration": '{"status": "ok"}',
    "connect_client": '{"connection_id": "conn-001"}',
    "broadcast": '{"status": "ok", "recipients": 1}',
    "create_schedule": '{"id": 1, "name": "cleanup-logs", "expression": "0 3 * * *"}',
    "list_schedules": '{"schedules": [{"id": 1, "name": "cleanup-logs"}]}',
    "test_run": '{"status": "failed", "error": "timeout after 60s"}',
    "set_timeout": '{"status": "ok", "timeout_sec": 300}',
    "delete_schedule": '{"status": "ok", "deleted_id": 1}',
    "create_virtual_service": '{"name": "checkout-svc", "hosts": ["checkout.app.com"]}',
    "add_route": '{"status": "ok"}',
    "set_circuit_breaker": '{"status": "ok"}',
    "add_retry_policy": '{"status": "ok"}',
    "enable_mtls": '{"status": "ok", "namespace": "prod", "mode": "STRICT"}',
    "enable_audit": '{"status": "ok"}',
    "trail_create": '{"arn": "arn:aws:cloudtrail:us-east-1:123456789012:trail/org-trail"}',
    "stream_to_lambda": '{"status": "ok"}',
    "query_athena": '{"rows": [{"event_name": "CreateBucket", "count": 150}], "execution_id": "q-001"}',
    "visualize": '{"url": "s3://reports/audit-chart.png"}',
    "create_flag": '{"id": "flag-dark-mode", "name": "dark-mode", "default": false}',
    "set_rule": '{"status": "ok"}',
    "evaluate": '{"result": true, "flag": "dark-mode", "context": {"country": "US"}}',
    "enable_for": '{"status": "ok"}',
    "delete_flag": '{"status": "ok", "deleted": "dark-mode"}',
    "list_zones": '{"zones": [{"id": "Z001", "name": "app.com."}]}',
    "create_zone": '{"id": "Z002", "name": "new-app.com."}',
    "export_records": '{"records": "www A 192.168.1.1\\nmail MX 10 mail.app.com."}',
    "import_records": '{"imported": 10}',
    "set_ttl": '{"status": "ok", "record": "www", "ttl": 60}',
    "test_resolve": '{"resolved": "192.168.1.1", "domain": "www.new-app.com"}',
    "get_cost": '{"total": 4523.12, "by_service": {"ec2": 2100.50, "rds": 1200.30, "lambda": 422.32}}',
    "create_budget": '{"status": "ok", "budget_id": "budget-ec2", "name": "ec2-budget"}',
    "set_anomaly_detection": '{"status": "ok", "sensitivity": "medium"}',
    "get_recommendations": '{"recommendations": [{"resource": "i-overprovisioned", "action": "downsize", "savings_pct": 30}]}',
    "apply_rightsizing": '{"status": "ok", "resource": "i-overprovisioned", "action": "downsize"}',
    "export_report": '{"url": "s3://reports/cost-report.pdf"}',
    "create_function": '{"arn": "arn:aws:lambda:us-east-1:123456789012:function:order-processor"}',
    "add_trigger": '{"status": "ok"}',
    "set_env": '{"status": "ok"}',
    "set_memory": '{"status": "ok", "memory_mb": 512}',
    "invoke": '{"status_code": 200, "result": "order processed"}',
    "view_logs": '{"logs": "2026-05-13T21:00:01 START RequestId\\n2026-05-13T21:00:02 END RequestId"}',
    "load_dataset": '{"rows": 10000, "columns": ["feature1", "feature2", "label"], "path": "s3://ml-data/train.csv"}',
    "preprocess": '{"status": "ok", "train_rows": 8000, "test_rows": 2000}',
    "train_model": '{"model_id": "mdl-001", "accuracy": 0.942, "algo": "xgboost"}',
    "evaluate": '{"accuracy": 0.938, "precision": 0.94, "recall": 0.93, "f1": 0.935}',
    "deploy_model": '{"endpoint": "prod-endpoint", "status": "deployed"}',
    "replicate_bucket": '{"status": "ok", "src": "us-east-1", "dst": "eu-west-1"}',
    "create_read_replica": '{"id": "rr-001", "region": "eu-west-1", "instance": "db.r5.large"}',
    "promote_replica": '{"status": "ok", "promoted": "rr-001"}',
    "failover_test": '{"status": "ok", "downtime_seconds": 12}',
    "verify_sync": '{"in_sync": true, "src_rows": 100000, "dst_rows": 100000}',
    "create_replica": '{"id": "replica-001", "source": "prod-pg"}',
    "configure_read_pool": '{"status": "ok", "min": 5, "max": 50}',
    "set_weight": '{"status": "ok", "replica": "replica-001", "weight": 50}',
    "monitor_replica_lag": '{"lag_seconds": 2, "status": "healthy"}',
    "promote": '{"status": "ok", "promoted": "replica-001"}',
    "list_certs": '{"certs": [{"arn": "arn:aws:acm:...", "expires_in_days": 14, "domain": "api.app.com"}]}',
    "renew_cert": '{"status": "ok", "new_arn": "arn:aws:acm:...", "expiry": "2027-05-13"}',
    "validate_dns": '{"valid": true, "domain": "api.app.com"}',
    "update_listener": '{"status": "ok", "listener": "arn:aws:elasticloadbalancing:..."}',
    "test_tls": '{"status": "ok", "cert_valid": true, "protocol": "TLSv1.3"}',
    "create_snapshot": '{"snapshot_id": "snap-002", "volume": "vol-src"}',
    "start_migration": '{"task_id": "mig-001", "status": "started"}',
    "check_status": '{"task_id": "mig-001", "status": "FAILED", "error": "source volume detached"}',
    "rollback_migration": '{"status": "ok", "rolled_back_from": "mig-001"}',
    "alert": '{"status": "sent", "channel": "pagerduty"}',
    "list_clusters": '{"clusters": [{"name": "prod-cluster", "env": "production"}, {"name": "staging-cluster"}]}',
    "describe_nodegroup": '{"name": "app-ng", "desired": 5, "available": 3, "status": "degraded"}',
    "scale_nodegroup": '{"status": "ok", "desired": 5}',
    "cordon": '{"status": "ok", "node": "ip-10-0-1-42"}',
    "drain": '{"status": "ok"}',
    "api_call": '{"status_code": 200, "body": {"item": "widget", "qty": 5}}',
    "check_rate_limit": '{"remaining": 8, "limit": 100, "window_sec": 60}',
    "get_quota": '{"quota": 100, "used": 92, "remaining": 8}',
    "wait": '{"status": "ok", "waited_ms": 1000}',
    "whoami": '{"user": "dev-user", "arn": "arn:aws:iam::123456789012:user/dev-user", "groups": ["engineers"]}',
    "list_permissions": '{"permissions": ["s3:ListBucket", "ec2:DescribeInstances"], "resource": "backup-bucket"}',
    "request_access": '{"request_id": "req-001", "status": "pending_approval"}',
    "approve_access": '{"status": "approved", "request_id": "req-001"}',
    "execute": '{"status": "ok", "action": "upload", "resource": "backup-bucket", "file": "data.zip"}',
    "create_env": '{"id": "env-green-001", "name": "green", "config": "api-svc"}',
    "deploy_build": '{"status": "ok", "env": "green", "build": "b-42"}',
    "switch_traffic": '{"status": "ok", "from": "blue", "to": "green", "pct": 100}',
    "smoke_test": '{"status": "ok", "tests_passed": 15, "tests_failed": 0}',
    "terminate_env": '{"status": "ok", "terminated": "blue"}',
    "deploy": '{"status": "ok", "build": "v2.1.0", "service": "payment-api"}',
    "check_alerts": '{"alerts": [{"severity": "CRITICAL", "service": "payment-api", "metric": "error_rate", "value": 0.15}]}',
    "check_logs": '{"logs": ["2026-05-13T21:03:12 ERROR payment-api: postgres pool exhausted"]}',
    "check_health": '{"status": "degraded", "db": "down", "cache": "ok"}',
    "scale_up": '{"status": "ok", "replicas": 6}',
    "check_metrics": '{"latency_p99": 6.2, "error_rate": 0.15, "cpu": 0.92}',
    "restart_service": '{"status": "ok", "healthy_pods": 3}',
    "increase_pool": '{"status": "ok", "max_connections": 200}',
    "verify_fix": '{"status": "healthy", "latency_p99": 0.3, "error_rate": 0.002}',
    "check_replica_lag": '{"lag_seconds": 300, "status": "degraded"}',
    "check_disk": '{"usage_pct": 97, "volume": "/data", "status": "critical"}',
    "cleanup_disk": '{"status": "ok", "freed_gb": 120}',
    "db_migrate": '{"status": "ok", "migration": "v042", "checks_passed": 3}',
    "check_cert": '{"expires_in_days": 14, "status": "warning"}',
    "check_deploy": '{"status": "ok", "version": "v2.1.0", "deployed_at": "2026-05-13T20:52Z"}',
    "check_traffic": '{"requests": 15000, "error_rate": 0.15, "p99_latency": 6.0}',
    "trace_request": '{"spans": [{"service": "api-gateway", "duration_ms": 120}, {"service": "orders", "duration_ms": 5800}], "root_cause": "payment timeout"}',
    "check_config": '{"feature_flags": {"new_checkout": true, "use_v2_payment": true}, "pool_size": 50}',
    "set_config": '{"status": "ok", "changed": ["use_v2_payment"]}',
    "validate_schema": '{"valid": true, "violations": []}',
    "run_diagnostics": '{"findings": [{"severity": "HIGH", "message": "connection pool exhausted"}]}',
}


@tool
def mock_api():
    """Execute a mock cloud API operation. Returns JSON result."""

    async def execute(operation: str, params: str = "{}") -> str:
        """Execute a mock cloud API operation.

        Args:
            operation: The API operation to perform (e.g. 'store_secret', 'check_status')
            params: JSON-encoded parameters for the operation
        """
        result = _default_results.get(operation, json.dumps({"status": "ok", "operation": operation}))
        return result

    return execute


# ---------------------------------------------------------------------------
# Tool-call scorer — validates mock_api call sequences
# ---------------------------------------------------------------------------
# Agentic solver — multi-turn for system_design / incident_scenarios
# ---------------------------------------------------------------------------


_default_results: dict[str, str] = {
    "deploy": "OK - latest build v2.1.0 deployed at 2026-05-13T21:00:00Z",
    "check_alerts": "CRITICAL: payment-api error_rate=15% (norm <1%), latency_p99=6s (norm 200ms)",
    "check_logs": "2026-05-13T21:03:12 ERROR: postgres connection pool exhausted: 0/100 slots free. Stack: OrderService.checkout() → PaymentGateway.charge()",
    "check_health": '{"status": "degraded", "checks": {"db": "down", "cache": "ok", "queue": "degraded"}}',
    "rollback": "OK - reverted payment-api from v2.1.0 to v2.0.9. Need to monitor for 5 min.",
    "scale_up": "OK - scaled payment-api replicas from 3 to 6. Rolling update initiated.",
    "check_metrics": '{"latency_p99": 6.2, "error_rate": 0.15, "cpu": 0.92, "memory": 0.87}',
    "restart_service": "OK - service payment-api restarted. 0/3 pods healthy.",
    "increase_pool": "OK - postgres max_connections set to 200. Existing connections drained.",
    "verify_fix": '{"status": "healthy", "latency_p99": 0.3, "error_rate": 0.002}',
    "check_replica_lag": '{"lag_seconds": 300, "status": "degraded"}',
    "promote_replica": "OK - read replica promoted to primary.",
    "failover": "OK - DNS updated, connections draining.",
    "check_disk": '{"usage_pct": 97, "volume": "/data", "status": "critical"}',
    "cleanup_disk": "OK - old WAL files archived, freed 120GB.",
    "db_migrate": "OK - migration v042 applied successfully. 3/3 checks passed.",
    "check_cert": '{"expires_in_days": 14, "status": "warning"}',
    "renew_cert": "OK - certificate renewed, new expiry: 2027-05-13.",
    "test_endpoint": '{"status": "ok", "response_code": 200, "latency_ms": 45}',
    "check_deploy": "OK - last deploy v2.1.0 by engineer-at 20:52Z.",
    "check_traffic": '{"total_requests": 15000, "error_rate": 0.15, "p99_latency": 6.0}',
    "trace_request": '{"spans": [{"service": "api-gateway", "duration_ms": 120}, {"service": "orders", "duration_ms": 5800}, {"service": "payment", "duration_ms": 8900}], "root_cause": "payment timeout"}',
    "check_config": '{"feature_flags": {"new_checkout": true, "use_v2_payment": true}, "pool_size": 50, "timeout_ms": 30000}',
    "set_config": "OK - feature flag 'use_v2_payment' set to false.",
    "validate_schema": '{"valid": true, "violations": []}',
    "check_data_integrity": '{"corrupted_rows": 42, "table": "orders", "status": "needs_repair"}',
    "repair_data": "OK - 42 corrupted rows in orders table repaired from WAL.",
    "run_diagnostics": '{"findings": [{"severity": "HIGH", "message": "connection pool exhausted"}, {"severity": "MEDIUM", "message": "slow query detected"}]}',
    "get_cost": '{"total": 4523.12, "by_service": {"ec2": 2100.50, "rds": 1200.30, "lambda": 422.32}}',
    "create_budget": "OK - budget 'ec2-budget' created at $5000.00 with thresholds [50, 80, 100].",
}


def _score_tool_sequence(scoring_cfg: dict, state: TaskState) -> tuple[float, str]:
    expected = scoring_cfg.get("expected", [])
    tool_calls = _extract_tool_calls(state.messages)
    actual_ops = [tc["op"] for tc in tool_calls]

    if not expected:
        return (1.0, "no expected calls specified")

    total_checks = 0
    passed_checks = 0
    detail_parts = []

    for i, exp in enumerate(expected):
        total_checks += 1
        exp_op = exp.get("operation", "")

        if i < len(actual_ops):
            actual_op = actual_ops[i]
            if actual_op == exp_op:
                passed_checks += 1
                detail_parts.append(f"call[{i}]={exp_op} ok")
                for k, v in exp.get("args_contain", {}).items():
                    total_checks += 1
                    tc_params = tool_calls[i].get("params_obj", {})
                    if tc_params.get(k) == v:
                        passed_checks += 1
                        detail_parts.append(f"  {k}={v} ok")
                    else:
                        detail_parts.append(f"  {k}={v} got={tc_params.get(k)!r}")
            else:
                detail_parts.append(f"call[{i}] exp={exp_op} got={actual_op}")
        else:
            detail_parts.append(f"call[{i}]={exp_op} MISSING")

    value = passed_checks / max(1, total_checks)
    return (value, "; ".join(detail_parts))


def _extract_tool_calls(messages: list) -> list[dict]:
    calls = []
    for msg in messages:
        for tc in getattr(msg, "tool_calls", None) or []:
            fn = getattr(tc, "function", "")
            raw_args = getattr(tc, "arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = {}
            params_raw = args.get("params", "{}")
            if isinstance(params_raw, str):
                try:
                    params_obj = json.loads(params_raw) if params_raw else {}
                except (json.JSONDecodeError, TypeError):
                    params_obj = {}
            else:
                params_obj = params_raw if isinstance(params_raw, dict) else {}
            calls.append({
                "op": args.get("operation", fn),
                "fn": fn,
                "args": args,
                "params_obj": params_obj,
            })
    return calls


@scorer(metrics=[accuracy(), stderr()])
def hybrid_scorer() -> Scorer:
    """Handles tool_sequence and regular text scoring in one category.

    - If scoring type is 'tool_sequence': validates mock_api call sequences
    - If 'agentic_quality': checks tool calls + meaningful final answer
    - Otherwise: delegates to scoring.py (deterministic text scorers)
    """

    async def score(state: TaskState, target: Target) -> Score:
        scoring_cfg = (state.metadata or {}).get("scoring") or {}
        stype = scoring_cfg.get("type", "")

        response = state.output.completion or ""

        reasoning_text = ""
        try:
            last_assistant = next(
                m for m in reversed(state.messages) if getattr(m, "role", "") == "assistant"
            )
            reasoning_text = getattr(last_assistant, "reasoning", None) or ""
            if not reasoning_text:
                extra = getattr(last_assistant, "model_extra", None) or {}
                reasoning_text = extra.get("reasoning_content", "") or ""
        except StopIteration:
            pass

        if stype == "tool_sequence":
            value, explanation = _score_tool_sequence(scoring_cfg, state)
        elif stype == "agentic_quality":
            tool_calls = _extract_tool_calls(state.messages)
            has_answer = len(response.strip()) > 50
            num_calls = len(tool_calls)
            checks = [
                ("final_answer", has_answer),
                ("tools_used", num_calls > 0),
                ("multi_turn", num_calls >= 3),
            ]
            passed = sum(1 for _, ok in checks if ok)
            value = passed / len(checks)
            explanation = (f"tools={num_calls} multi_turn={num_calls>=3} "
                           f"final_answer={has_answer}")
        else:
            value, explanation = score_response(response, scoring_cfg)
            if not response and reasoning_text:
                explanation = (
                    f"empty content (model used budget on thinking, "
                    f"{len(reasoning_text)} chars). " + explanation
                )

        if value >= 0.999:
            label = CORRECT
        elif value <= 0.001:
            label = INCORRECT
        else:
            label = PARTIAL

        return Score(
            value=value,
            answer=response[:300],
            explanation=explanation,
            metadata={
                "label": label,
                "scoring_type": stype,
                "reasoning_chars": len(reasoning_text),
            },
        )

    return score


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_category(category: str) -> list[Sample]:
    yaml_path = TASKS_DIR / f"{category}.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    samples: list[Sample] = []
    for t in data.get("tasks", []):
        prompt = _expand_fillers(t["prompt"])
        if "system" in t:
            input_msgs = [
                ChatMessageSystem(content=t["system"]),
                ChatMessageUser(content=prompt),
            ]
        else:
            input_msgs = prompt
        samples.append(
            Sample(
                id=t["id"],
                input=input_msgs,
                target="",
                metadata={
                    "scoring": t["scoring"],
                    "max_tokens": t.get("max_tokens", 512),
                    "temperature": t.get("temperature", 0.0),
                },
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Custom scorer — dispatches to scoring.py based on sample metadata
# ---------------------------------------------------------------------------


@scorer(metrics=[accuracy(), stderr()])
def sanity_scorer() -> Scorer:
    """Reads `metadata.scoring` per sample and dispatches to scoring.py.

    Captures `reasoning_content` (chain-of-thought from local thinking models)
    separately so it's recorded in the eval log but does not pollute the score.
    """

    async def score(state: TaskState, target: Target) -> Score:
        response = state.output.completion or ""

        reasoning_text = ""
        try:
            last_assistant = next(
                m for m in reversed(state.messages) if getattr(m, "role", "") == "assistant"
            )
            reasoning_text = getattr(last_assistant, "reasoning", None) or ""
            if not reasoning_text:
                extra = getattr(last_assistant, "model_extra", None) or {}
                reasoning_text = extra.get("reasoning_content", "") or ""
        except StopIteration:
            pass

        scoring_cfg = (state.metadata or {}).get("scoring") or {}
        value, explanation = score_response(response, scoring_cfg)

        if not response and reasoning_text:
            explanation = (
                f"empty content (model used budget on thinking, "
                f"{len(reasoning_text)} chars). " + explanation
            )

        if value >= 0.999:
            label = CORRECT
        elif value <= 0.001:
            label = INCORRECT
        else:
            label = PARTIAL

        return Score(
            value=value,
            answer=response[:300],
            explanation=explanation,
            metadata={
                "label": label,
                "scoring_type": scoring_cfg.get("type"),
                "reasoning_chars": len(reasoning_text),
            },
        )

    return score


# ---------------------------------------------------------------------------
# Task builders
# ---------------------------------------------------------------------------


def _build_task(category: str) -> Task:
    samples = _load_category(category)
    if not samples:
        raise ValueError(f"No samples in tasks/{category}.yaml")
    max_tok = max(s.metadata.get("max_tokens", 512) for s in samples)
    temp = max(s.metadata.get("temperature", 0.0) for s in samples)
    return Task(
        dataset=samples,
        solver=generate(),
        scorer=sanity_scorer(),
        config=GenerateConfig(max_tokens=max_tok, temperature=temp),
    )


def _build_tool_task(category: str) -> Task:
    samples = _load_category(category)
    if not samples:
        raise ValueError(f"No samples in tasks/{category}.yaml")
    max_tok = max(s.metadata.get("max_tokens", 512) for s in samples)
    temp = max(s.metadata.get("temperature", 0.0) for s in samples)
    return Task(
        dataset=samples,
        solver=generate(),
        scorer=hybrid_scorer(),
        tools=[mock_api()],
        config=GenerateConfig(max_tokens=max_tok, temperature=temp),
    )


def _build_agentic_task(category: str) -> Task:
    samples = _load_category(category)
    if not samples:
        raise ValueError(f"No samples in tasks/{category}.yaml")
    max_tok = max(s.metadata.get("max_tokens", 512) for s in samples)
    temp = max(s.metadata.get("temperature", 0.0) for s in samples)
    return Task(
        dataset=samples,
        solver=generate(),
        scorer=hybrid_scorer(),
        tools=[mock_api()],
        config=GenerateConfig(max_tokens=max_tok, temperature=temp),
    )


# ---------------------------------------------------------------------------
# @task functions, one per category. These MUST be top-level for inspect-ai
# to discover them via AST parsing.
# ---------------------------------------------------------------------------


@task
def general_knowledge() -> Task:
    return _build_task("general_knowledge")


@task
def common_sense() -> Task:
    return _build_task("common_sense")


@task
def math() -> Task:
    return _build_task("math")


@task
def reasoning() -> Task:
    return _build_task("reasoning")


@task
def coding() -> Task:
    return _build_task("coding")


@task
def coding_debug() -> Task:
    return _build_task("coding_debug")


@task
def system_design() -> Task:
    return _build_task("system_design")


@task
def instruction_following() -> Task:
    return _build_task("instruction_following")


@task
def creative_writing() -> Task:
    return _build_task("creative_writing")


@task
def writing() -> Task:
    return _build_task("writing")


@task
def structured_synthesis() -> Task:
    return _build_task("structured_synthesis")


@task
def structured_output() -> Task:
    return _build_task("structured_output")


@task
def safety() -> Task:
    return _build_task("safety")


@task
def tool_use() -> Task:
    return _build_tool_task("tool_use")


@task
def incident_scenarios() -> Task:
    return _build_agentic_task("incident_scenarios")


@task
def multilingual() -> Task:
    return _build_task("multilingual")


@task
def long_context() -> Task:
    return _build_task("long_context")
