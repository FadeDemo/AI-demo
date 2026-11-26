from dataclasses import dataclass


@dataclass
class StreamResponseTiming:
    ttft_seconds: float | None = None
    total_seconds: float | None = None
