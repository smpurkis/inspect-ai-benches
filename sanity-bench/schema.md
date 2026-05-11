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
