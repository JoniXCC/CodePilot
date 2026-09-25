from reports.class_report import build_report
from reports.stats import average, summarize_scores


def test_average():
    assert average([50, 70, 90]) == 70


def test_summary():
    assert summarize_scores([40, 60]) == {"count": 2, "average": 50.0, "best": 60}


def test_empty_class_summary():
    assert summarize_scores([]) == {"count": 0, "average": 0.0, "best": 0}


def test_report_lists_every_class():
    assert build_report({"B": [80], "A": [60, 70]}) == [
        "A: 2 students, average 65.0",
        "B: 1 students, average 80.0",
    ]
