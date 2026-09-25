"""Prepare (or reset) the demo projects.

    python -m app.demo

Copies every folder in examples/ into PROJECTS_DIR as a fresh git repository,
so CodePilot has real repos to work on and a demo can be re-run from scratch.
"""

from app.config import REPO_ROOT, get_settings
from app.services.repo_copies import create_git_copy


def main() -> None:
    settings = get_settings()
    examples = REPO_ROOT / "examples"
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    for example in sorted(p for p in examples.iterdir() if p.is_dir()):
        destination = create_git_copy(example, settings.projects_dir / example.name)
        print(f"Prepared {destination}")


if __name__ == "__main__":
    main()
