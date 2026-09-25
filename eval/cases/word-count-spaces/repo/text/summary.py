from text.analysis import reading_time_minutes, word_count


def article_stats(body: str) -> str:
    return f"{word_count(body)} words · {reading_time_minutes(body)} min read"
