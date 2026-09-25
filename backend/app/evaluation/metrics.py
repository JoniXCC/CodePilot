"""Scoring helpers and the report format for evaluation runs."""

import difflib
from datetime import datetime, timezone

from pydantic import BaseModel, Field

LOCATION_TOLERANCE_LINES = 2


class CaseResult(BaseModel):
    case_id: str
    bug_description: str
    expected_file: str
    status: str  # agent result status, or "error" if the harness itself failed
    tests_failed_before: bool  # sanity check: the case really reproduces a bug
    found_correct_file: bool
    found_bug_location: bool
    patch_applied: bool
    tests_passed: bool  # full suite green after the patch AND the expected test ran
    touched_protected_files: bool  # e.g. the agent edited the tests instead of the code
    successful_fix: bool
    tool_calls: int = 0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    files_modified: list[str] = Field(default_factory=list)
    error: str | None = None


class EvalReport(BaseModel):
    generated_at: datetime
    provider: str
    model: str | None
    cases: int
    correct_file: int
    correct_location: int
    successful_fixes: int
    tests_passed: int
    average_tool_calls: float
    average_duration_ms: float
    total_input_tokens: int
    total_output_tokens: int
    results: list[CaseResult]


def changed_line_ranges(original: str | None, proposed: str) -> list[tuple[int, int]]:
    """1-based line ranges of the *original* file that an edit touched (insertions map to the line they follow)."""
    before = (original or "").splitlines()
    after = proposed.splitlines()
    ranges: list[tuple[int, int]] = []
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        start = i1 + 1
        end = max(i2, start)  # a pure insertion has i1 == i2
        ranges.append((start, end))
    return ranges


def touches_expected_lines(ranges: list[tuple[int, int]], expected: tuple[int, int], tolerance: int = LOCATION_TOLERANCE_LINES) -> bool:
    low, high = expected[0] - tolerance, expected[1] + tolerance
    return any(start <= high and end >= low for start, end in ranges)


def build_report(results: list[CaseResult], provider: str, model: str | None) -> EvalReport:
    count = len(results)
    return EvalReport(
        generated_at=datetime.now(timezone.utc),
        provider=provider,
        model=model,
        cases=count,
        correct_file=sum(r.found_correct_file for r in results),
        correct_location=sum(r.found_bug_location for r in results),
        successful_fixes=sum(r.successful_fix for r in results),
        tests_passed=sum(r.tests_passed for r in results),
        average_tool_calls=round(sum(r.tool_calls for r in results) / count, 1) if count else 0.0,
        average_duration_ms=round(sum(r.duration_ms for r in results) / count) if count else 0.0,
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
        results=results,
    )


def format_report(report: EvalReport) -> str:
    n = report.cases
    lines = [
        "Agent Evaluation",
        f"Provider: {report.provider}" + (f" ({report.model})" if report.model else ""),
        f"Cases: {n}",
        f"Correct file identified: {report.correct_file}/{n}",
        f"Correct bug location: {report.correct_location}/{n}",
        f"Successful fixes: {report.successful_fixes}/{n}",
        f"Tests passed after patch: {report.tests_passed}/{n}",
        f"Average tool calls: {report.average_tool_calls:.1f}",
        f"Average time: {report.average_duration_ms / 1000:.1f}s",
        "",
        f"{'case':<26} {'file':<5} {'loc':<5} {'tests':<6} {'fix':<5} {'calls':>5}  note",
    ]
    mark = lambda ok: "yes" if ok else "no"  # noqa: E731
    for r in report.results:
        note = r.error or ("edited protected files" if r.touched_protected_files else "")
        lines.append(
            f"{r.case_id:<26} {mark(r.found_correct_file):<5} {mark(r.found_bug_location):<5} "
            f"{mark(r.tests_passed):<6} {mark(r.successful_fix):<5} {r.tool_calls:>5}  {note}"
        )
    return "\n".join(lines)
