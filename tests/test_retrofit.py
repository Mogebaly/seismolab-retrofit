import pytest
from retrofit import evaluator as E

OK = {"jacket_mm": [10, 10, 10], "brace_mm2": [100, 100, 100]}

@pytest.mark.parametrize("bad", [
    {"jacket_mm": [0, 0, 0]},
    {"jacket_mm": [0, 0], "brace_mm2": [0, 0, 0]},
    {"jacket_mm": [-1, 0, 0], "brace_mm2": [0, 0, 0]},
    {"jacket_mm": [0, 0, 0], "brace_mm2": [0, 0, 5000]},
    {"jacket_mm": [float("nan"), 0, 0], "brace_mm2": [0, 0, 0]},
    {"jacket_mm": [True, 0, 0], "brace_mm2": [0, 0, 0]},
])
def test_rejects_malformed(bad):
    with pytest.raises(ValueError):
        E.validate(bad)

def test_cost_monotonic_and_zero():
    assert E.cost({"jacket_mm": [0]*3, "brace_mm2": [0]*3}) == 0
    assert E.cost(OK) < E.cost({"jacket_mm": [20]*3, "brace_mm2": [100]*3}) < E.cost({"jacket_mm": [20]*3, "brace_mm2": [300]*3})

def test_over_budget_scores_zero_without_analysis():
    r = E.evaluate({"jacket_mm": [150]*3, "brace_mm2": [4000]*3})
    assert r["score"] == 0.0 and r["gate"] == "over_budget"

def test_nonconverged_record_scores_zero():
    assert E.record_score({"converged": False, "drift": float("inf"), "acc": float("inf")}) == 0.0

def test_scoring_ramps():
    assert E.record_score({"converged": True, "drift": 0.0, "acc_over_pga": 0.0}) == pytest.approx(1.0)
    assert E.record_score({"converged": True, "drift": E.DRIFT_LIMIT, "acc_over_pga": E.ACC_LIMIT}) == 0.0

def test_deterministic():
    a = E.evaluate(OK, E.PUBLIC_SUITE[:1]); b = E.evaluate(OK, E.PUBLIC_SUITE[:1])
    assert a["score"] == b["score"]

def test_retrofit_stiffens_frame():
    nodes = E.build({"jacket_mm": [0]*3, "brace_mm2": [0]*3})
    import openseespy.opensees as ops
    d0 = None
    def period(d):
        E.build(d); import math
        lam = ops.eigen(2); return 2*math.pi/math.sqrt(lam[0])
    assert period({"jacket_mm": [60]*3, "brace_mm2": [1000]*3}) < period({"jacket_mm": [0]*3, "brace_mm2": [0]*3})

import json, pytest
from retrofit import evaluator as E2

@pytest.mark.parametrize("text", ['{"jacket_mm":[NaN,0,0],"brace_mm2":[0,0,0]}', '[1,2,3]', '{"jacket_mm":[0,0,0],"brace_mm2":[0,0,0],"x":1}', '{"jacket_mm":"abc","brace_mm2":[0,0,0]}'])
def test_strict_loader_rejects(tmp_path, text):
    p = tmp_path / "d.json"; p.write_text(text)
    with pytest.raises(ValueError):
        E2.validate(E2.load_design(str(p)))

def test_absolute_accel_includes_ground():
    # near-rigid retrofit: absolute floor accel should be at least ~PGA (relative accel alone would be far below)
    d = {"jacket_mm": [100]*3, "brace_mm2": [3000]*3}
    nodes = E2.build(d); rec, dt = E2.synthetic_record(101, 0.3)
    m = E2.run_record(d, rec, dt, nodes)
    assert m["converged"] and m["acc_over_pga"] > 0.9

def test_nonconverged_gets_zero_even_with_good_looking_metrics():
    assert E2.record_score({"converged": False, "drift": 0.0, "acc": 0.0, "acc_over_pga": 0.0}) == 0.0

import subprocess, sys, json as _json

def _cli(path, *extra):
    out = subprocess.run([sys.executable, "-m", "retrofit.evaluator", str(path), "--suite", "public", *extra], capture_output=True, text=True)
    line = [l for l in out.stdout.splitlines() if l.startswith("RESULT_JSON ")][-1]
    return out.returncode, _json.loads(line[len("RESULT_JSON "):])

@pytest.mark.parametrize("text", ['{"jacket_mm":[NaN,0,0],"brace_mm2":[0,0,0]}', 'not json', '{"jacket_mm":[0,0,0]}', '[]', ''])
def test_cli_invalid_submissions_give_structured_error(tmp_path, text):
    p = tmp_path / "d.json"; p.write_text(text)
    code, r = _cli(p)
    assert code == 2 and r["score"] == 0.0 and r["error"]

def test_cli_missing_file_structured_error(tmp_path):
    code, r = _cli(tmp_path / "nope.json"); assert code == 2 and r["error"]

def test_cli_valid_submission_matches_schema_fields():
    code, r = _cli("retrofit/data/noop.json")
    assert code == 0 and r["error"] is None and r["gate"] == "ok" and len(r["records"]) == len(E2.PUBLIC_SUITE)
    sch = _json.load(open("retrofit/result.schema.json"))
    assert set(sch["required"]) <= set(r)

def test_solver_failure_scores_zero(monkeypatch):
    import openseespy.opensees as ops
    d = {"jacket_mm": [0, 0, 0], "brace_mm2": [0, 0, 0]}
    nodes = E2.build(d); rec, dt = E2.synthetic_record(101, 0.3)
    monkeypatch.setattr(ops, "analyze", lambda *a, **k: -3)    # every step "fails"
    m = E2.run_record(d, rec, dt, nodes)
    assert m["converged"] is False and E2.record_score(m) == 0.0

def test_input_schema_file_matches_validator_bounds():
    sch = _json.load(open("retrofit/schema.json"))["properties"]
    assert sch["jacket_mm"]["items"]["maximum"] == E2.JACKET_MAX and sch["brace_mm2"]["items"]["maximum"] == E2.BRACE_MAX
