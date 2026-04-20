"""Subset URL loading for analysis/report_all_tools.py."""

from __future__ import annotations

import json
from pathlib import Path


def test_subset_from_golden_first_n(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    g.write_text(
        json.dumps(
            [
                {"url": "https://github.com/o/r/pull/1"},
                {"url": "https://github.com/o/r/pull/2"},
                {"url": "https://github.com/o/r/pull/3"},
            ]
        )
    )
    from analysis.report_all_tools import _load_subset_urls

    class A:
        subset_urls_file = None
        subset_from_golden = g
        subset_limit = 2

    s, ordered = _load_subset_urls(A())
    assert s == {
        "https://github.com/o/r/pull/1",
        "https://github.com/o/r/pull/2",
    }
    assert ordered == [
        "https://github.com/o/r/pull/1",
        "https://github.com/o/r/pull/2",
    ]


def test_subset_urls_file_skips_comments(tmp_path: Path) -> None:
    f = tmp_path / "u.txt"
    f.write_text(
        "# header\n"
        "https://github.com/a/b/pull/9\n"
        "\n"
        "https://github.com/c/d/pull/1\n"
    )
    from analysis.report_all_tools import _load_subset_urls

    class A:
        subset_urls_file = f
        subset_from_golden = None
        subset_limit = None

    s, ordered = _load_subset_urls(A())
    assert len(s) == 2
    assert "https://github.com/a/b/pull/9" in s
