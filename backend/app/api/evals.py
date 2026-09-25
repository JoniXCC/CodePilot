import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import REPO_ROOT

router = APIRouter(prefix="/evals", tags=["evals"])

LATEST_RESULTS = REPO_ROOT / "eval" / "results" / "latest.json"


@router.get("/latest")
def latest_eval_results() -> dict[str, Any]:
    """The most recent report written by `python -m eval.run_eval`."""
    if not LATEST_RESULTS.is_file():
        raise HTTPException(status_code=404, detail="No evaluation results yet. Run the evaluation script first.")
    return json.loads(LATEST_RESULTS.read_text(encoding="utf-8"))
