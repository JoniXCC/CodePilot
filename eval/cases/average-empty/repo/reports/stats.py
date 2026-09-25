def average(values: list[float]) -> float:
    return sum(values) / len(values)


def summarize_scores(scores: list[float]) -> dict[str, float]:
    return {
        "count": len(scores),
        "average": round(average(scores), 2),
        "best": max(scores, default=0),
    }
