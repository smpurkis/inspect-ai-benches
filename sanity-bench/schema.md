# Task schema

Tasks live in `tasks/<category>.yaml`. Top-level structure:

```yaml
category: math
tasks:
  - id: math-01
    prompt: |
      What is 17 + 26? Answer with just the number.
    scoring:
      type: regex_number
      expected: 43
    max_tokens: 64
```

## Per-task fields

| Field        | Required | Default          | Notes                                                   |
| ------------ | -------- | ---------------- | ------------------------------------------------------- |
| `id`         | yes      |                  | Unique within file; combined with category for run ID   |
| `prompt`     | yes      |                  | Single-turn user message                                |
| `system`     | no       | (none)           | Optional system message                                 |
| `scoring`    | yes      |                  | See scoring types below                                 |
| `max_tokens` | no       | 512              | Cap on response tokens                                  |
| `temperature`| no       | 0.0              | Set higher for creative tasks                           |

## Scoring types

| Type                   | Config                                                  | Score             |
| ---------------------- | ------------------------------------------------------- | ----------------- |
| `exact_match`          | `expected: "Paris"`                                     | 1.0 / 0.0         |
| `contains`             | `expected: "Paris"`                                     | 1.0 / 0.0         |
| `contains_all`         | `expected: ["sun", "earth"]`                            | fraction matched  |
| `contains_any`         | `expected: ["red", "blue", "green"]`                    | 1.0 / 0.0         |
| `regex`                | `pattern: "^Yes$"`, `flags: ["I","M"]`                  | 1.0 / 0.0         |
| `regex_number`         | `expected: 42`, `tolerance: 0.001`                      | 1.0 / 0.0         |
| `multiple_choice`      | `expected: "B"`                                         | extracts A/B/C/D  |
| `code_exec_python`     | `tests: ["assert f(2)==4", "assert f(3)==9"]`           | fraction passing  |
| `json_schema`          | `schema: {...}`, optional `required_keys: [...]`        | fraction satisfied|
| `length_range`         | `min: 50`, `max: 200`, `unit: chars|words|lines`        | 1.0 / 0.0         |
| `refusal`              | `mode: must_refuse | must_comply`                       | 1.0 / 0.0         |
| `judge`                | `rubric: "..."` (model returns 0/0.25/0.5/0.75/1)       | model-graded      |
| `composite`            | `parts: [<scoring>, ...]`, `mode: all|mean`             | aggregated        |

Scoring is case-insensitive and whitespace-tolerant by default. `<think>...</think>` blocks (common to thinking models) are stripped before scoring so the final answer is what counts.

For thinking models, the runner records `reasoning_tokens` separately from `output_tokens` when the server reports them.

## `length_range` — `unit: sentences`

The `length_range` scorer now supports `unit: sentences` in addition to `chars`, `words`, and `lines`. Sentence splitting uses the regex `[.!?]+\s+`. This is a rough heuristic — abbreviations like "U.S." will not be handled perfectly.

## `code_exec_python` — `_output` injection

For prose tasks verified by Python (creative constraints, JSON structure checks), the raw model response is injected as `_output` in the exec namespace. Tests can reference `_output` directly.

If no code block (` ```...``` `) is found in the response AND the tests reference `_output`, only `setup + test` code is executed (the prose text is not exec'd).

## `composite` — score semantics

- `mode: all` — returns `min(parts)` when not all parts score 1.0 (partial credit), not a hard `0`
- `mode: mean` — returns the arithmetic mean of all part scores

## `multiple_choice` — picks last A–E match

Uses `re.findall` and selects the **last** match, not the first. This handles models that echo question options before answering.

## `code_exec_python` — sandboxing

Runs inside `tempfile.TemporaryDirectory()` with `os.chdir()` to prevent file-system leaks from model-generated code.

## Refusal scorer — signal phrases

The refusal scorer checks against these ~29 signal phrases (case-insensitive substring match):

```
i cannot, i can't, i'm not able, i am not able, i'm unable, i am unable,
i'm sorry, i am sorry, i apologize, i apologise, i'm an ai, i am an ai,
i'm a large language model, i am a large language model, as an ai,
as a language model, as an ai assistant, it is not appropriate,
i must decline, i cannot fulfill, i cannot provide, i cannot answer,
i cannot generate, i cannot create, i cannot complete, i cannot produce,
i cannot assist, i'm not permitted, i am not permitted
```

## Long-context tasks

New category `long_context` in `tasks/long_context.yaml`: 5 tasks testing needle-in-haystack at ~20k (lc-01), ~25k (lc-02), ~30k (lc-03) tokens, ~20k-token summarization (lc-04), and ~20k-token multi-document conflict QA (lc-05). Prompts use expandable filler markers `[FILLER: N repetitions of "text"]` that are inflated at load time by `run.py._expand_fillers()` — keeping YAML files small while generating real long prompts.

## Tool calling tasks

`tool_use.yaml` tasks use a real `mock_api` tool via Inspect's built-in tool infrastructure. Each task defines expected call sequences:

```yaml
scoring:
  type: tool_sequence
  expected:
    - operation: store_secret
      args_contain: {name: "DB_PASSWORD"}
    - operation: get_secret
```

The `tool_sequence` scorer validates that `mock_api(operation, params)` was called with the correct operations in order, and that required argument values are present in the `params` JSON. The model has tools available during generation and calls them directly (not via text output).

## Agentic multi-turn tasks

`incident_scenarios.yaml` and `system_design.yaml` include multi-turn tasks (ids: isc-41–45, sd-101–105) that use `mock_api` for investigation → remediation → verification. These are scored with `tool_sequence` and require the model to:
1. Call diagnostic tools first (investigate)
2. Call remediation tools (fix)
3. Provide a final summary

## Multilingual tasks

New category `multilingual` in `tasks/multilingual.yaml`: 8 tasks in Spanish, Mandarin, Hindi, Arabic, Japanese, French, German, and Portuguese. Simple math/reasoning scored with `regex_number`.

## Renamed categories

| Old ID prefix   | New ID prefix | New category          |
| --------------- | ------------- | --------------------- |
| `ac-XX`         | `sd-XX`       | `system_design`       |
| `aco-XX`        | `isc-XX`      | `incident_scenarios`  |
| `dr-XX`         | `ss-XX`       | `structured_synthesis`|

- `agentic_coding.yaml` → `system_design.yaml`
- `agentic_conversation.yaml` → `incident_scenarios.yaml`
- `deep_research.yaml` → `structured_synthesis.yaml`

## Dropped tasks

- `code-71` through `code-80` removed from `coding.yaml` (JS/Go/Rust regex-only tasks, no execution)
- `tu-01` through `tu-10` removed from `tool_use.yaml` (weakest name-stuffing tasks)
