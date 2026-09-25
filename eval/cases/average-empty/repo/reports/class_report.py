from reports.stats import summarize_scores


def build_report(classes: dict[str, list[float]]) -> list[str]:
    lines = []
    for name, scores in sorted(classes.items()):
        summary = summarize_scores(scores)
        lines.append(f"{name}: {summary['count']} students, average {summary['average']}")
    return lines
