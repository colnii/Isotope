from __future__ import annotations

from isotope.features.research.source_classification import classify_research_source


def test_classify_research_source_marks_official_docs_high_authority():
    classification = classify_research_source(
        {
            "title": "Python documentation",
            "url": "https://docs.python.org/3/library/urllib.parse.html",
        }
    )

    assert classification == {
        "source_kind": "official_docs",
        "source_authority": "high",
    }


def test_classify_research_source_marks_papers_high_authority():
    classification = classify_research_source(
        {
            "title": "Attention Is All You Need",
            "url": "https://arxiv.org/abs/1706.03762",
        }
    )

    assert classification == {
        "source_kind": "paper",
        "source_authority": "high",
    }


def test_classify_research_source_marks_community_low_authority():
    classification = classify_research_source(
        {
            "title": "Discussion thread",
            "url": "https://reddit.com/r/Python/comments/example",
        }
    )

    assert classification == {
        "source_kind": "community",
        "source_authority": "low",
    }


def test_classify_research_source_marks_unknown_when_host_is_unrecognized():
    classification = classify_research_source(
        {
            "title": "Personal note",
            "url": "https://example.net/research-note",
        }
    )

    assert classification == {
        "source_kind": "unknown",
        "source_authority": "unknown",
    }
