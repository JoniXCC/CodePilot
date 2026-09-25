from text.analysis import reading_time_minutes, word_count
from text.summary import article_stats


def test_simple_sentence():
    assert word_count("the quick brown fox") == 4


def test_extra_whitespace_is_ignored():
    assert word_count("hello  world\nagain ") == 3


def test_empty_text():
    assert word_count("") == 0


def test_reading_time():
    assert reading_time_minutes("word " * 400) == 2


def test_article_stats():
    assert article_stats("one two three") == "3 words · 1 min read"
