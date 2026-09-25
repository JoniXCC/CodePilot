def word_count(text: str) -> int:
    if not text:
        return 0
    return len(text.split(" "))


def reading_time_minutes(text: str, words_per_minute: int = 200) -> int:
    return max(1, round(word_count(text) / words_per_minute))
