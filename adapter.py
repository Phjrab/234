"""Extension typing contract for local training events.

The deployed implementation lives in training.py and train_worker.py.
This Protocol remains a reference for future independent adapter integrations.
"""
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol


@dataclass(frozen=True)
class TrainingEvent:
    version: Literal[1]
    run_id: str
    sequence: int
    timestamp: str
    kind: Literal['metric', 'log', 'checkpoint', 'status', 'telemetry']
    payload: Mapping[str, object]


class LocalTrainingAdapter(Protocol):
    """Extension interface; the demo simulator remains synthetic."""

    def validate(self, config: Mapping[str, object]) -> list[str]: ...

    def start(self, run_id: str, config: Mapping[str, object],
              emit: Callable[[TrainingEvent], None]) -> None: ...

    def cancel(self, run_id: str) -> None: ...

    def capabilities(self) -> Mapping[str, bool]: ...
