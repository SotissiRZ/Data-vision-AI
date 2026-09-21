from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")


def test_insight_limitations_are_captured_before_jsx():
    assert "const limitations:string[]=feed?.limitations??[];" in PAGE
    assert "limitations.length>0" in PAGE
    assert "limitations.map((x:string)" in PAGE
    assert "feed.limitations.map" not in PAGE


def test_v2531_keeps_insight_feed_optional_until_data_is_loaded():
    assert "const [feed,setFeed]=useState<AnyObj|null>(null);" in PAGE
    assert "feed?.summary?.count??0" in PAGE
