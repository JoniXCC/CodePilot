"""Tests for the evaluation harness - including negative controls, so a perfect score means something."""

import shutil
from pathlib import Path

import pytest

from app.evaluation.cases import EvalCase, load_cases
from app.evaluation.metrics import build_report, changed_line_ranges, touches_expected_lines
from app.evaluation.runner import reference_provider, run_case
from app.llm.scripted_provider import ScriptedProvider, ScriptedStep

ALL_CASES = load_cases()
needs_npm = pytest.mark.skipif(shutil.which("npm") is None, reason="Node.js/npm not installed")


def case(case_id: str) -> EvalCase:
    return next(c for c in ALL_CASES if c.id == case_id)


# --- metrics --------------------------------------------------------------------------


def test_changed_line_ranges_replacement() -> None:
    assert changed_line_ranges("a\nb\nc\n", "a\nB\nc\n") == [(2, 2)]


def test_changed_line_ranges_insertion_maps_to_following_line() -> None:
    assert changed_line_ranges("a\nb\n", "a\nnew\nb\n") == [(2, 2)]


def test_changed_line_ranges_new_file() -> None:
    assert changed_line_ranges(None, "x\ny\n") == [(1, 1)]


@pytest.mark.parametrize(("ranges", "expected"), [([(6, 6)], True), ([(5, 5)], False), ([(12, 12)], True), ([(13, 20)], False), ([], False)])
def test_touches_expected_lines_with_tolerance(ranges: list[tuple[int, int]], expected: bool) -> None:
    assert touches_expected_lines(ranges, (8, 10)) is expected


def test_report_aggregates() -> None:
    report = build_report([], "reference", None)
    assert report.cases == 0 and report.average_tool_calls == 0


# --- dataset integrity ----------------------------------------------------------------


def test_cases_are_well_formed() -> None:
    assert len(ALL_CASES) >= 10
    assert len({c.id for c in ALL_CASES}) == len(ALL_CASES)
    for c in ALL_CASES:
        assert (c.source_dir / c.expected_file).is_file(), c.id
        assert c.reference_fix, c.id
        assert not c.is_protected(c.expected_file), c.id
        for edit in c.reference_fix:
            source = (c.source_dir / edit.path).read_text(encoding="utf-8")
            assert source.count(edit.old) == 1, f"{c.id}: reference 'old' must match exactly once"


@pytest.mark.parametrize("eval_case", [c for c in ALL_CASES if c.language == "python"], ids=lambda c: c.id)
def test_python_cases_reproduce_and_reference_fix_solves_them(eval_case: EvalCase, tmp_path: Path) -> None:
    result = run_case(eval_case, reference_provider, tmp_path)
    assert result.tests_failed_before, "the case must reproduce the bug"
    assert result.successful_fix and result.found_bug_location, result


@needs_npm
@pytest.mark.parametrize("eval_case", [c for c in ALL_CASES if c.language == "javascript"], ids=lambda c: c.id)
def test_javascript_cases_reproduce_and_reference_fix_solves_them(eval_case: EvalCase, tmp_path: Path) -> None:
    result = run_case(eval_case, reference_provider, tmp_path)
    assert result.tests_failed_before, "the case must reproduce the bug"
    assert result.successful_fix and result.found_bug_location, result


# --- negative controls: the harness must detect failure -------------------------------


def test_agent_that_changes_nothing_scores_zero(tmp_path: Path) -> None:
    result = run_case(case("average-empty"), lambda _c: ScriptedProvider([]), tmp_path)
    assert result.tests_failed_before
    assert not (result.found_correct_file or result.found_bug_location or result.tests_passed or result.successful_fix)


def test_editing_the_tests_is_not_a_fix(tmp_path: Path) -> None:
    cheat = [ScriptedStep(tool="replace_code", arguments={
        "path": "tests/test_stats.py",
        "old_code": 'assert summarize_scores([]) == {"count": 0, "average": 0.0, "best": 0}',
        "new_code": "pass",
    })]
    result = run_case(case("average-empty"), lambda _c: ScriptedProvider(cheat), tmp_path)
    assert result.touched_protected_files
    assert not result.tests_passed  # the original tests were restored before re-running
    assert not result.successful_fix


def test_fix_in_the_wrong_place_is_scored_as_such(tmp_path: Path) -> None:
    # Guarding in the caller makes the expected test pass, but misses the reported location.
    wrong_place = [ScriptedStep(tool="replace_code", arguments={
        "path": "reports/stats.py",
        "old_code": '        "average": round(average(scores), 2),',
        "new_code": '        "average": round(average(scores), 2) if scores else 0.0,',
    })]
    result = run_case(case("average-empty"), lambda _c: ScriptedProvider(wrong_place), tmp_path)
    assert result.found_correct_file
    assert not result.found_bug_location
    assert result.successful_fix  # behaviourally fixed - location is reported as a separate metric
