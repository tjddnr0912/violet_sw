"""Tests for editorial C3 data blocks (deterministic markdown tables)."""

from shared.editorial.data_blocks import markdown_table, news_quality_block


def test_markdown_table_shape():
    out = markdown_table(["A", "B"], [(1, 2), (3, 4)])
    lines = out.splitlines()
    assert lines[0] == "| A | B |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| 1 | 2 |"
    assert lines[3] == "| 3 | 4 |"


def test_markdown_table_pads_short_rows():
    out = markdown_table(["A", "B", "C"], [(1,)])
    assert out.splitlines()[-1] == "| 1 |  |  |"


def test_news_quality_block_renders_counts_and_ratios():
    stats = {
        "total": 20,
        "by_category": {"정치": 3, "경제": 8, "사회": 9},
        "tier1_ratio": 0.45,
        "korean_ratio": 0.55,
    }
    out = news_quality_block(stats)
    assert "총 20건" in out
    assert "## 이번 호 수집 데이터" in out
    # 카테고리는 건수 내림차순
    body = out.splitlines()
    table_rows = [l for l in body if l.startswith("| ") and "카테고리" not in l and "---" not in l]
    assert table_rows[0].startswith("| 사회 | 9")   # 최다 먼저
    assert "45%" in out                              # Tier-1
    assert "국내 **55%** / 해외 **45%**" in out


def test_news_quality_block_empty_on_no_data():
    assert news_quality_block({}) == ""
    assert news_quality_block({"total": 0}) == ""
    assert news_quality_block(None) == ""
