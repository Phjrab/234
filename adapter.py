"""Future local worker contract, deliberately not wired to the demo server.

No worker implementation, subprocess launch, GPU probing or network client exists
here. A real adapter must enforce the controls documented in adapter-contract.md.
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
    """Proposed interface only; demo simulator is not a real adapter."""

    def validate(self, config: Mapping[str, object]) -> list[str]: ...

    def start(self, run_id: str, config: Mapping[str, object],
              emit: Callable[[TrainingEvent], None]) -> None: ...

    def cancel(self, run_id: str) -> None: ...

    def capabilities(self) -> Mapping[str, bool]: ...
