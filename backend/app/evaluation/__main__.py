"""Run the evaluation suite.

    python -m app.evaluation                 # the configured LLM (needs an API key)
    python -m app.evaluation --reference     # the known reference fixes (no API key; validates the harness)
    python -m app.evaluation --cases age-boundary,average-empty
"""

import argparse
import sys
import tempfile
from pathlib import Path

from app.config import REPO_ROOT, get_settings
from app.evaluation.cases import load_cases
from app.evaluation.metrics import build_report, format_report
from app.evaluation.runner import ProviderFactory, reference_provider, run_case
from app.llm.factory import create_provider
from app.logging_config import configure_logging

RESULTS_DIR = REPO_ROOT / "eval" / "results"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the CodePilot agent on known bugs")
    parser.add_argument("--reference", action="store_true", help="use the reference fixes instead of an LLM")
    parser.add_argument("--cases", help="comma-separated case ids (default: all)")
    parser.add_argument("--max-steps", type=int, default=None)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    configure_logging("WARNING")
    cases = load_cases(only=args.cases.split(",") if args.cases else None)

    if args.reference:
        factory: ProviderFactory = reference_provider
        provider_name, model = "reference", None
    else:
        factory = lambda _case: create_provider(settings)  # noqa: E731
        provider_name, model = settings.llm_provider, settings.model_name

    results = []
    with tempfile.TemporaryDirectory(prefix="codepilot-eval-", ignore_cleanup_errors=True) as workdir:
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] {case.id} ...", end=" ", flush=True)
            result = run_case(case, factory, Path(workdir), args.max_steps or settings.agent_max_steps,
                              settings.command_timeout_seconds)
            print("fixed" if result.successful_fix else f"not fixed ({result.error or result.status})", flush=True)
            results.append(result)

    report = build_report(results, provider_name, model)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump_json(indent=2)
    stamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / f"{stamp}-{provider_name}.json").write_text(payload, encoding="utf-8")
    (RESULTS_DIR / "latest.json").write_text(payload, encoding="utf-8")
    print("\n" + format_report(report))


if __name__ == "__main__":
    main()
