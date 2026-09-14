from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
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

DEFAULT_INPUTS_PATH = PROJECT_ROOT / "samples" / "sampling-experiment" / "inputs.json"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
SamplingParameter = Literal["temperature", "top_p"]


@dataclass(frozen=True)
class ExperimentInput:
    input_id: str
    prompt: str


@dataclass(frozen=True)
class ExperimentSummary:
    attempted: int
    succeeded: int
    failed: int


def load_experiment_inputs(path: Path) -> list[ExperimentInput]:
    with path.open(encoding="utf-8") as input_file:
        raw_inputs = json.load(input_file)
    if not isinstance(raw_inputs, list):
        raise ValueError("Experiment inputs must be a JSON array.")

    inputs: list[ExperimentInput] = []
    for index, raw_input in enumerate(raw_inputs, start=1):
        if not isinstance(raw_input, dict):
            raise ValueError(f"Experiment input {index} must be a JSON object.")
        input_id = raw_input.get("id")
        prompt = raw_input.get("prompt")
        if not isinstance(input_id, str) or not input_id.strip():
            raise ValueError(f"Experiment input {index} has an invalid id.")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Experiment input {input_id!r} has an invalid prompt.")
        inputs.append(ExperimentInput(input_id=input_id, prompt=prompt))

    input_ids = [experiment_input.input_id for experiment_input in inputs]
    if len(inputs) != 10:
        raise ValueError(
            f"Exactly 10 experiment inputs are required; got {len(inputs)}."
        )
    if len(set(input_ids)) != len(input_ids):
        raise ValueError("Experiment input ids must be unique.")
    return inputs


def validate_experiment_settings(
    *,
    config: ModelConfig,
    parameter: SamplingParameter,
    values: Sequence[float],
    runs: int,
    max_output_tokens: int,
) -> None:
    if config.provider != "openai":
        raise ValueError("Sampling experiments require PROVIDER=openai.")
    if len(values) != 3 or len(set(values)) != 3:
        raise ValueError("Provide exactly three distinct sampling values.")
    if runs < 2:
        raise ValueError("At least two runs are required.")
    if max_output_tokens <= 0:
        raise ValueError("max-output-tokens must be greater than zero.")

    model_profile = config.model_profile
    parameter_config = (
        model_profile.temperature_config
        if parameter == "temperature"
        else model_profile.top_p_config
    )
    minimum = (
        parameter_config.min_temperature
        if parameter == "temperature"
        else parameter_config.min_top_p
    )
    maximum = (
        parameter_config.max_temperature
        if parameter == "temperature"
        else parameter_config.max_top_p
    )
    for value in values:
        if not minimum <= value <= maximum:
            raise ValueError(
                f"{parameter} value {value} is outside the model range "
                f"[{minimum}, {maximum}]."
            )


def run_experiment(
    *,
    client: ModelClient,
    config: ModelConfig,
    inputs: Sequence[ExperimentInput],
    parameter: SamplingParameter,
    values: Sequence[float],
    runs: int,
    max_output_tokens: int,
    system_prompt: str,
    write_record: Callable[[dict[str, Any]], None],
    experiment_id: str | None = None,
    timestamp_factory: Callable[[], datetime] | None = None,
) -> ExperimentSummary:
    validate_experiment_settings(
        config=config,
        parameter=parameter,
        values=values,
        runs=runs,
        max_output_tokens=max_output_tokens,
    )
    if len(inputs) != 10:
        raise ValueError(
            f"Exactly 10 experiment inputs are required; got {len(inputs)}."
        )

    experiment_id = experiment_id or str(uuid4())
    timestamp_factory = timestamp_factory or (lambda: datetime.now(UTC))
    attempted = 0
    succeeded = 0
    failed = 0

    for run_number in range(1, runs + 1):
        for value in values:
            for experiment_input in inputs:
                attempted += 1
                temperature = (
                    value if parameter == "temperature" else config.temperature
                )
                top_p = value if parameter == "top_p" else config.top_p
                request = ModelRequest(
                    messages=[
                        Message(role="system", content=system_prompt),
                        Message(role="user", content=experiment_input.prompt),
                    ],
                    reserved_output_tokens=max_output_tokens,
                    reasoning_effort=config.reasoning_effort,
                    temperature=temperature,
                    top_p=top_p,
                )
                record: dict[str, Any] = {
                    "schema_version": 1,
                    "experiment_id": experiment_id,
                    "request_number": attempted,
                    "requested_at": timestamp_factory().isoformat(),
                    "run": run_number,
                    "input_id": experiment_input.input_id,
                    "input": experiment_input.prompt,
                    "provider": config.provider,
                    "model": config.model,
                    "varied_parameter": parameter,
                    "parameter_value": value,
                    "parameters": {
                        "temperature": temperature,
                        "top_p": top_p,
                        "reasoning_effort": config.reasoning_effort,
                        "max_output_tokens": max_output_tokens,
                    },
                    "system_prompt": system_prompt,
                    "judgement": {
                        "status": "pending",
                        "quality": None,
                        "notes": "",
                    },
                }
                try:
                    response = client.send(request)
                except Exception as error:
                    failed += 1
                    record.update(
                        {
                            "status": "failed",
                            "error_type": type(error).__name__,
                            "error": str(error),
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
                            "status": (
                                "succeeded" if completed_normally else "incomplete"
                            ),
                            "output": response.text,
                            "finish_reason": response.reason,
                            "usage": asdict(response.usage),
                        }
                    )
                write_record(record)

    return ExperimentSummary(
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the generation-parameters sampling experiment as independent requests."
        )
    )
    parser.add_argument(
        "--parameter",
        choices=("temperature", "top_p"),
        required=True,
        help="The only sampling parameter varied between groups.",
    )
    parser.add_argument(
        "--values",
        type=float,
        nargs=3,
        required=True,
        metavar=("LOW", "MEDIUM", "HIGH"),
        help="Exactly three distinct values for the selected parameter.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Number of complete repetitions; must be at least 2 (default: 2).",
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=DEFAULT_INPUTS_PATH,
        help=f"JSON file containing exactly 10 fixed inputs (default: {DEFAULT_INPUTS_PATH}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New JSONL result path. Existing files are never overwritten.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=512,
        help="Fixed output budget for every request (default: 512).",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="Fixed system prompt used by every request.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_model_config()
        inputs = load_experiment_inputs(args.inputs)
        validate_experiment_settings(
            config=config,
            parameter=args.parameter,
            values=args.values,
            runs=args.runs,
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
                    f"run={record['run']} input={record['input_id']} "
                    f"{record['varied_parameter']}={record['parameter_value']}",
                    file=sys.stderr,
                )

            summary = run_experiment(
                client=client,
                config=config,
                inputs=inputs,
                parameter=args.parameter,
                values=args.values,
                runs=args.runs,
                max_output_tokens=args.max_output_tokens,
                system_prompt=args.system_prompt,
                write_record=write_record,
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Sampling experiment failed: {error}", file=sys.stderr)
        return 2

    print(
        f"Finished: attempted={summary.attempted} succeeded={summary.succeeded} "
        f"failed={summary.failed} output={args.output}",
        file=sys.stderr,
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
