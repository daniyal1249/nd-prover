from dataclasses import dataclass, field
from pathlib import Path

from nd_prover import *


@dataclass
class BenchmarkCase:
    library: str
    version: str
    problem_id: str
    source_path: Path
    problem: Problem
    source_status: str = None
    source_rating: float = None
    source_logic: str = None
    source_domain: str = None
    metadata: dict = field(default_factory=dict)

    @property
    def case_id(self):
        parts = [self.library, self.problem_id, self.problem.logic.__name__]
        if self.source_domain:
            parts.append(self.source_domain)
        return ":".join(parts)

    @property
    def expected_status(self):
        if self.metadata.get("exclude_from_gold"):
            return None
        return {
            "Theorem": "valid",
            "Non-Theorem": "invalid"
        }.get(self.source_status)


@dataclass(frozen=True)
class SkippedProblem:
    library: str
    problem_id: str
    source_path: Path
    reason: str
    detail: str = ""

