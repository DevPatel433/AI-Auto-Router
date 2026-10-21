import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.pop("ANTHROPIC_API_KEY", None)  # force offline heuristic mode
from router import Router, classify_heuristic, ROUTES


def test_coding():
    assert classify_heuristic("Debug this Python function")["category"] == "coding"


def test_writing():
    assert classify_heuristic("Draft an email and rewrite the tone")["category"] == "writing"


def test_research():
    assert classify_heuristic("Compare and summarize recent papers")["category"] == "research"


def test_default_on_no_signal():
    assert classify_heuristic("hello")["category"] == "research"


def test_router_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = Router().run("Write a poem about rain", dry=True)
    assert res["category"] == "writing"
    assert res["model"] == ROUTES["writing"].model
    assert res["response"] is None


def test_dashboard_stats(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import dashboard
    r = Router()
    r.run("Write a poem about rain", dry=True)
    r.run("Debug this python function", dry=True)
    s = dashboard.compute_stats()
    assert s["total"] == 2
    assert s["categories"] == {"writing": 1, "coding": 1}
    out = dashboard.build_report(str(tmp_path / "report.html"))
    assert "Debug this python function" in open(out).read()
