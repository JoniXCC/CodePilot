"""Evaluation cases: small repositories with a known bug, described in eval/cases/<id>/case.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config import REPO_ROOT

CASES_DIR = REPO_ROOT / "eval" / "cases"


class ReferenceEdit(BaseModel):
    path: str
    old: str
    new: str


class EvalCase(BaseModel):
    id: str
    language: str
    bug_description: str
    expected_file: str
    expected_lines: tuple[int, int] = Field(description="1-based inclusive range where the bug lives")
    expected_test: str = Field(description="Name of the test that must pass once the bug is fixed")
    test_command: str
    protected_paths: list[str] = Field(default_factory=list, description="Paths the fix must not change (tests)")
    reference_fix: list[ReferenceEdit] = Field(default_factory=list)
    repo_path: str | None = None  # defaults to the case's repo/ folder
    source_dir: Path = Path()  # filled in by load_cases

    def is_protected(self, path: str) -> bool:
        return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in self.protected_paths)


def load_case(case_dir: Path) -> EvalCase:
    data = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    case = EvalCase.model_validate(data)
    case.source_dir = (case_dir / (case.repo_path or "repo")).resolve()
    if not case.source_dir.is_dir():
        raise ValueError(f"{case.id}: repository folder not found at {case.source_dir}")
    return case


def load_cases(cases_dir: Path = CASES_DIR, only: list[str] | None = None) -> list[EvalCase]:
    cases = [load_case(d) for d in sorted(cases_dir.iterdir()) if (d / "case.yaml").is_file()]
    if only:
        unknown = set(only) - {c.id for c in cases}
        if unknown:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c.id in only]
    return cases
