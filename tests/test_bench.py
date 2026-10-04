import json

import pytest

from testomation import bench
from testomation.runner import parse_report


def test_catalogue_loads_and_every_bug_names_a_reference_spec():
    variants = bench.load_catalogue()
    specs = {p.stem for p in bench.REFERENCE.glob("*.json")}
    bugs = [v for v in variants if v.kind == "bug"]
    assert bugs and all(v.catches in specs for v in bugs)
    assert any(v.held_out for v in bugs)
    assert {v.kind for v in variants} == {"bug", "noise", "flaky"}


def test_catalogue_rejects_a_bug_without_catches(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text('[[variant]]\nid="x"\nkind="bug"\ncategory="c"\ndescription="d"\n')
    with pytest.raises(ValueError, match="needs `catches`"):
        bench.load_catalogue(bad)


def test_span_reports_mean_and_range():
    assert bench.span([1.0, 0.5, 1.0]) == {"mean": 0.833, "min": 0.5, "max": 1.0}


def test_replay_reports_baseline():
    r = bench.run_replay()
    assert r["cases"] == sum(r["labels"].values())
    assert 0 < r["baselines"]["everything_is_a_bug"] < 1


REPORT = {"suites": [{"suites": [{"specs": [
    {"title": "ref01",
     "tests": [{"annotations": [], "results": [{"status": "passed", "attachments": []}]}]},
    {"title": "ref02", "tests": [{
        "annotations": [{"type": "failing-step", "description": "3"}],
        "results": [
            {"status": "failed", "error": {"message": "\x1b[31mTimeout\x1b[39m"}, "attachments": [
                {"name": "signals", "contentType": "application/json",
                 "body": "W3sia2luZCI6ImNvbnNvbGUiLCJ0ZXh0IjoiYm9vbSJ9XQ=="}]},
            {"status": "passed", "attachments": []}]}]},
]}]}]}


def test_parse_report_reads_attempts_steps_and_signals():
    by_id = {t.spec_id: t for t in parse_report(REPORT)}
    assert by_id["ref01"].passed and not by_id["ref01"].flaky
    t = by_id["ref02"]
    assert t.passed and t.flaky
    first = t.attempts[0]
    assert first.failing_step == 3
    assert first.error == "Timeout"  # ANSI colour codes stripped
    assert first.signals == [{"kind": "console", "text": "boom"}]


def test_reference_specs_are_schema_valid():
    from jsonschema import Draft202012Validator
    schema = json.loads((bench.ROOT / "schemas" / "test-spec.schema.json").read_text())
    v = Draft202012Validator(schema)
    for p in bench.REFERENCE.glob("*.json"):
        assert not list(v.iter_errors(json.loads(p.read_text()))), p.name
