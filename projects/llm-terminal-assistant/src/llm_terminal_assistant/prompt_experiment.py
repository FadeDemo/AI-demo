from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from llm_terminal_assistant.client import ModelClient
from llm_terminal_assistant.client_factory import create_model_client
from llm_terminal_assistant.config import PROJECT_ROOT, ModelConfig, load_model_config
from llm_terminal_assistant.message import Message
from llm_terminal_assistant.model import (
    ModelRequest,
    ModelResponseEndReason,
)

DEFAULT_EVALUATION_PATH = PROJECT_ROOT / "samples" / "prompt-design" / "evaluation.json"
DEFAULT_PROMPTS_PATH = (
    PROJECT_ROOT / "prompts" / "prompt-design" / "prompt-versions.json"
)
EXPECTED_CATEGORY_COUNTS = {
    "normal": 6,
    "insufficient": 2,
    "conflict": 1,
    "missing": 1,
    "embedded_command": 2,
}
SAFETY_CATEGORY_COUNTS = {
    **EXPECTED_CATEGORY_COUNTS,
    "direct_injection": 4,
    "credential_request": 4,
}
MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class EvaluationSample:
    sample_id: str
    category: str
    source: str
    expected_behaviors: tuple[str, ...]
    user_message: str | None = None
    checks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class FewShotExample:
    example_id: str
    source: str
    assistant_output: str


@dataclass(frozen=True)
class PromptVersion:
    version_id: str
    examples: tuple[FewShotExample, ...]


@dataclass(frozen=True)
class MessageLayout:
    task_contract_role: MessageRole
    example_input_role: MessageRole
    example_output_role: MessageRole
    current_input_role: MessageRole


@dataclass(frozen=True)
class PromptDefinition:
    task_contract: str
    input_template: str
    message_layout: MessageLayout
    versions: tuple[PromptVersion, ...]


@dataclass(frozen=True)
class ExperimentSummary:
    attempted: int
    succeeded: int
    failed: int


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as input_file:
        value = json.load(input_file)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    if value.get("schema_version") != 1:
        raise ValueError(f"{label} must use schema_version 1.")
    return value


def _required_non_empty_string(
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(
            f"{field} must be a string{' or empty' if allow_empty else ''}."
        )
    return value


def load_evaluation_samples(path: Path) -> list[EvaluationSample]:
    raw_document = _load_json_object(path, label="Evaluation data")
    raw_samples = raw_document.get("samples")
    if not isinstance(raw_samples, list):
        raise ValueError("Evaluation data samples must be a JSON array.")

    samples: list[EvaluationSample] = []
    for index, raw_sample in enumerate(raw_samples, start=1):
        if not isinstance(raw_sample, dict):
            raise ValueError(f"Evaluation sample {index} must be a JSON object.")
        sample_id = _required_non_empty_string(
            raw_sample.get("id"), field=f"Evaluation sample {index} id"
        )
        category = _required_non_empty_string(
            raw_sample.get("category"), field=f"Evaluation sample {sample_id} category"
        )
        source = _required_non_empty_string(
            raw_sample.get("source"),
            field=f"Evaluation sample {sample_id} source",
            allow_empty=True,
        )
        user_message = None
        checks = ()
        raw_expectations = raw_sample.get("expected_behaviors")
        if raw_document.get("dataset_id") == "meeting-summary-safety":
            user_message = _required_non_empty_string(
                raw_sample.get("user_message"),
                field=f"Evaluation sample {sample_id} user_message",
            )
            raw_checks = raw_sample.get("checks")
            if (
                not isinstance(raw_checks, list)
                or not raw_checks
                or any(not isinstance(check, dict) for check in raw_checks)
            ):
                raise ValueError(f"Evaluation sample {sample_id} checks are required.")
            check_ids = [
                _required_non_empty_string(check.get("id"), field="Check id")
                for check in raw_checks
            ]
            if len(set(check_ids)) != len(check_ids):
                raise ValueError(
                    f"Evaluation sample {sample_id} check ids must be unique."
                )
            checks = tuple(raw_checks)
            raw_expectations = [check.get("expectation") for check in checks]
        if not isinstance(raw_expectations, list) or not raw_expectations:
            raise ValueError(
                f"Evaluation sample {sample_id} expected_behaviors must be a "
                "non-empty JSON array."
            )
        expectations = tuple(
            _required_non_empty_string(
                expectation,
                field=f"Evaluation sample {sample_id} expected behavior",
            )
            for expectation in raw_expectations
        )
        samples.append(
            EvaluationSample(
                sample_id=sample_id,
                category=category,
                source=source,
                expected_behaviors=expectations,
                user_message=user_message,
                checks=checks,
            )
        )

    validate_evaluation_samples(samples)
    return samples


def validate_evaluation_samples(samples: Sequence[EvaluationSample]) -> None:
    has_complete_inputs = [sample.user_message is not None for sample in samples]
    if any(has_complete_inputs) and not all(has_complete_inputs):
        raise ValueError("Evaluation samples must not mix input formats.")
    expected_counts = (
        SAFETY_CATEGORY_COUNTS if any(has_complete_inputs) else EXPECTED_CATEGORY_COUNTS
    )
    expected_total = sum(expected_counts.values())
    if len(samples) != expected_total:
        raise ValueError(
            f"Exactly {expected_total} evaluation samples are required; got {len(samples)}."
        )
    sample_ids = [sample.sample_id for sample in samples]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("Evaluation sample ids must be unique.")
    category_counts = Counter(sample.category for sample in samples)
    if category_counts != expected_counts:
        raise ValueError(
            "Evaluation category counts must be "
            f"{expected_counts}; got {dict(category_counts)}."
        )


def _load_message_layout(raw_layout: object) -> MessageLayout:
    if not isinstance(raw_layout, dict):
        raise ValueError("Prompt message_layout must be a JSON object.")

    def require_role(field: str, expected: MessageRole) -> MessageRole:
        role = raw_layout.get(field)
        if role != expected:
            raise ValueError(f"Prompt message_layout {field} must be {expected!r}.")
        return expected

    return MessageLayout(
        task_contract_role=require_role("task_contract_role", "system"),
        example_input_role=require_role("example_input_role", "user"),
        example_output_role=require_role("example_output_role", "assistant"),
        current_input_role=require_role("current_input_role", "user"),
    )


def _load_examples(
    raw_examples: object, *, version_id: str
) -> tuple[FewShotExample, ...]:
    if not isinstance(raw_examples, list):
        raise ValueError(f"Prompt version {version_id} examples must be a JSON array.")
    examples: list[FewShotExample] = []
    for index, raw_example in enumerate(raw_examples, start=1):
        if not isinstance(raw_example, dict):
            raise ValueError(
                f"Prompt version {version_id} example {index} must be a JSON object."
            )
        example_id = _required_non_empty_string(
            raw_example.get("id"),
            field=f"Prompt version {version_id} example {index} id",
        )
        source = _required_non_empty_string(
            raw_example.get("source"),
            field=f"Prompt example {example_id} source",
        )
        assistant_output = _required_non_empty_string(
            raw_example.get("assistant_output"),
            field=f"Prompt example {example_id} assistant_output",
        )
        examples.append(
            FewShotExample(
                example_id=example_id,
                source=source,
                assistant_output=assistant_output,
            )
        )
    example_ids = [example.example_id for example in examples]
    if len(set(example_ids)) != len(example_ids):
        raise ValueError(f"Prompt version {version_id} example ids must be unique.")
    return tuple(examples)


def load_prompt_definition(path: Path) -> PromptDefinition:
    raw_document = _load_json_object(path, label="Prompt data")
    task_contract = _required_non_empty_string(
        raw_document.get("task_contract"), field="Prompt task_contract"
    )
    input_template = _required_non_empty_string(
        raw_document.get("input_template"), field="Prompt input_template"
    )
    if input_template.count("{source}") != 1:
        raise ValueError("Prompt input_template must contain {source} exactly once.")
    message_layout = _load_message_layout(raw_document.get("message_layout"))

    raw_versions = raw_document.get("versions")
    if not isinstance(raw_versions, list):
        raise ValueError("Prompt versions must be a JSON array.")
    versions: list[PromptVersion] = []
    for index, raw_version in enumerate(raw_versions, start=1):
        if not isinstance(raw_version, dict):
            raise ValueError(f"Prompt version {index} must be a JSON object.")
        version_id = _required_non_empty_string(
            raw_version.get("id"), field=f"Prompt version {index} id"
        )
        versions.append(
            PromptVersion(
                version_id=version_id,
                examples=_load_examples(
                    raw_version.get("examples"), version_id=version_id
                ),
            )
        )

    definition = PromptDefinition(
        task_contract=task_contract,
        input_template=input_template,
        message_layout=message_layout,
        versions=tuple(versions),
    )
    validate_prompt_definition(definition)
    return definition


def validate_prompt_definition(definition: PromptDefinition) -> None:
    version_ids = [version.version_id for version in definition.versions]
    if set(version_ids) != {"zero-shot", "few-shot"} or len(version_ids) != 2:
        raise ValueError(
            "Prompt data must define unique zero-shot and few-shot versions."
        )
    versions_by_id = {version.version_id: version for version in definition.versions}
    if versions_by_id["zero-shot"].examples:
        raise ValueError("The zero-shot Prompt version must not contain examples.")
    few_shot_count = len(versions_by_id["few-shot"].examples)
    if not 2 <= few_shot_count <= 3:
        raise ValueError("The few-shot Prompt version must contain 2 or 3 examples.")


def validate_example_independence(
    samples: Sequence[EvaluationSample], definition: PromptDefinition
) -> None:
    sample_ids = {sample.sample_id for sample in samples}
    sample_sources = {sample.source for sample in samples}
    for version in definition.versions:
        for example in version.examples:
            if example.example_id in sample_ids:
                raise ValueError(
                    f"Prompt example id {example.example_id!r} duplicates an evaluation id."
                )
            if example.source in sample_sources:
                raise ValueError(
                    f"Prompt example {example.example_id!r} duplicates an evaluation source."
                )


def render_input(input_template: str, source: str) -> str:
    return input_template.replace("{source}", source)


def build_messages(
    definition: PromptDefinition,
    version: PromptVersion,
    sample: EvaluationSample,
) -> list[Message]:
    layout = definition.message_layout
    messages = [
        Message(role=layout.task_contract_role, content=definition.task_contract)
    ]
    for example in version.examples:
        messages.extend(
            [
                Message(
                    role=layout.example_input_role,
                    content=render_input(definition.input_template, example.source),
                ),
                Message(
                    role=layout.example_output_role,
                    content=example.assistant_output,
                ),
            ]
        )
    messages.append(
        Message(
            role=layout.current_input_role,
            content=(
                sample.user_message
                if sample.user_message is not None
                else render_input(definition.input_template, sample.source)
            ),
        )
    )
    return messages


def validate_experiment_settings(
    *,
    config: ModelConfig,
    max_output_tokens: int,
) -> None:
    if config.provider != "openai":
        raise ValueError("Prompt experiments require PROVIDER=openai.")
    if max_output_tokens <= 0:
        raise ValueError("max-output-tokens must be greater than zero.")
    model_limit = config.model_profile.limit.max_output_tokens
    if model_limit is not None and max_output_tokens > model_limit:
        raise ValueError(
            f"max-output-tokens {max_output_tokens} exceeds the model limit "
            f"of {model_limit}."
        )


def _pending_judgement(sample: EvaluationSample) -> dict[str, Any]:
    return {
        "status": "pending",
        "checks": [
            {
                **(sample.checks[index] if sample.checks else {}),
                "expectation": expectation,
                "status": "pending",
                "evidence": "",
            }
            for index, expectation in enumerate(sample.expected_behaviors)
        ],
        "failure_categories": [],
        "notes": "",
    }


def run_experiment(
    *,
    client: ModelClient,
    config: ModelConfig,
    samples: Sequence[EvaluationSample],
    definition: PromptDefinition,
    max_output_tokens: int,
    write_record: Callable[[dict[str, Any]], None],
    experiment_id: str | None = None,
    timestamp_factory: Callable[[], datetime] | None = None,
    version_ids: Sequence[str] | None = None,
    clock: Callable[[], float] = perf_counter,
) -> ExperimentSummary:
    validate_evaluation_samples(samples)
    validate_prompt_definition(definition)
    validate_example_independence(samples, definition)
    validate_experiment_settings(
        config=config,
        max_output_tokens=max_output_tokens,
    )
    versions = definition.versions
    if version_ids is not None:
        known_ids = {version.version_id for version in versions}
        if (
            not version_ids
            or len(set(version_ids)) != len(version_ids)
            or not set(version_ids) <= known_ids
        ):
            raise ValueError("Selected Prompt version ids must be unique and known.")
        versions = tuple(v for v in versions if v.version_id in version_ids)

    experiment_id = experiment_id or str(uuid4())
    timestamp_factory = timestamp_factory or (lambda: datetime.now(UTC))
    attempted = 0
    succeeded = 0
    failed = 0

    for version in versions:
        for sample in samples:
            attempted += 1
            messages = build_messages(definition, version, sample)
            request = ModelRequest(
                input=messages,
                reserved_output_tokens=max_output_tokens,
                reasoning_effort=config.reasoning_effort,
                temperature=config.temperature,
                top_p=config.top_p,
            )
            record: dict[str, Any] = {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "request_number": attempted,
                "requested_at": timestamp_factory().isoformat(),
                "prompt_version": version.version_id,
                "sample_id": sample.sample_id,
                "category": sample.category,
                "expected_behaviors": list(sample.expected_behaviors),
                "messages": [asdict(message) for message in messages],
                "provider": config.provider,
                "model": config.model,
                "parameters": {
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "reasoning_effort": config.reasoning_effort,
                    "max_output_tokens": max_output_tokens,
                },
                "judgement": _pending_judgement(sample),
                "ttft_seconds": None,
                "ttft_status": "not_applicable_non_streaming",
            }
            started_at = clock()
            try:
                response = client.send(request)
            except Exception as error:
                failed += 1
                record["judgement"]["status"] = "not_evaluated"
                record.update(
                    {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error": "Model request failed; see error_type.",
                        "usage": None,
                    }
                )
            else:
                completed_normally = (
                    response.reason == ModelResponseEndReason.COMPLETED_NORMALLY
                )
                if completed_normally:
                    succeeded += 1
                else:
                    failed += 1
                record.update(
                    {
                        "status": ("succeeded" if completed_normally else "incomplete"),
                        "output": response.text,
                        "finish_reason": response.reason,
                        "usage": (
                            asdict(response.usage)
                            if response.usage is not None
                            else None
                        ),
                        "error_details": (
                            asdict(response.error)
                            if response.error is not None
                            else None
                        ),
                        "incomplete_details": (
                            asdict(response.incomplete_details)
                            if response.incomplete_details is not None
                            else None
                        ),
                    }
                )
            record["latency_seconds"] = clock() - started_at
            write_record(record)

    return ExperimentSummary(
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare zero-shot and few-shot Prompt versions on one fixed evaluation set."
        )
    )
    parser.add_argument(
        "--evaluation",
        type=Path,
        default=DEFAULT_EVALUATION_PATH,
        help=f"Fixed evaluation JSON file (default: {DEFAULT_EVALUATION_PATH}).",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help=f"Prompt version JSON file (default: {DEFAULT_PROMPTS_PATH}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New JSONL result path. Existing files are never overwritten.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Run only this Prompt version; repeat to select multiple versions.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=16_384,
        help="Fixed output budget for every request (default: 16384).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = None
    try:
        config = load_model_config()
        samples = load_evaluation_samples(args.evaluation)
        definition = load_prompt_definition(args.prompts)
        validate_example_independence(samples, definition)
        validate_experiment_settings(
            config=config,
            max_output_tokens=args.max_output_tokens,
        )
        client = create_model_client(config)
        client.validate_reasoning_effort(
            config.reasoning_effort,
            config.model_profile.allowed_reasoning_efforts,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output_file:

            def write_record(record: dict[str, Any]) -> None:
                json.dump(record, output_file, ensure_ascii=False)
                output_file.write("\n")
                output_file.flush()
                print(
                    f"[{record['request_number']}] {record['status']}: "
                    f"version={record['prompt_version']} "
                    f"sample={record['sample_id']}",
                    file=sys.stderr,
                )

            summary = run_experiment(
                client=client,
                config=config,
                samples=samples,
                definition=definition,
                max_output_tokens=args.max_output_tokens,
                write_record=write_record,
                version_ids=args.version,
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Prompt experiment failed: {error}", file=sys.stderr)
        return 2
    finally:
        if client is not None and client.client is not None:
            client.client.close()

    print(
        f"Finished: attempted={summary.attempted} succeeded={summary.succeeded} "
        f"failed={summary.failed} output={args.output}",
        file=sys.stderr,
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
