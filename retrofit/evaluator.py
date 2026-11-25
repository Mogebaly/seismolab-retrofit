"""SeismoLab-Retrofit evaluator: retrofit a weak 3-story RC frame under a cost budget.

Units: N, mm, s. Design = per-story column jacket thickness (mm) + X-brace area (mm^2) in bay 1.
Ground motions are SYNTHETIC and PUBLIC (envelope-modulated sinusoids, seeds in this file), not real records and not a private/hidden evaluation.
A step that fails to converge after substepping counts as collapse: that record scores 0.
"""
from __future__ import annotations
import json, math, random
from dataclasses import dataclass
import openseespy.opensees as ops

H = [4000.0, 3000.0, 3000.0]        # soft first story
BAY, NB = 5000.0, 2
COL_B, COL_D, COVER, BAR = 300.0, 300.0, 40.0, 16.0
BEAM_B, BEAM_D = 250.0, 450.0
FPC, FY, ES = 20.0, 400.0, 200000.0
MASS_PER_FLOOR = 12.0             # tonne (N s^2/mm) per node
GRAV = 18.0                          # N/mm on beams
JACKET_MAX, BRACE_MAX = 150.0, 4000.0
COST_JACKET = 1.0e-3                 # cost units per mm^3-ish of added concrete (relative)
COST_BRACE = 8.0e-3                  # cost units per mm^3 of steel
BUDGET = 5.0e3
DRIFT_TARGET, DRIFT_LIMIT = 0.004, 0.020
ACC_TARGET, ACC_LIMIT = 1.0, 3.0    # peak ABSOLUTE floor accel as a multiple of the record PGA

def cost(design):
    c = 0.0
    for i, (t, a) in enumerate(zip(design["jacket_mm"], design["brace_mm2"])):
        added = ((COL_B + 2*t) * (COL_D + 2*t) - COL_B * COL_D) * H[i] * (NB + 1)
        c += COST_JACKET * added / 1.0e3
        c += COST_BRACE * a * math.hypot(BAY, H[i]) * 2 / 1.0e3
    return c

def validate(design):
    if not isinstance(design, dict): raise ValueError("design must be an object")
    if set(design) != {"jacket_mm", "brace_mm2"}: raise ValueError("keys must be jacket_mm, brace_mm2")
    for k, hi in (("jacket_mm", JACKET_MAX), ("brace_mm2", BRACE_MAX)):
        v = design[k]
        if not isinstance(v, list) or len(v) != 3: raise ValueError(f"{k} needs 3 values")
        for x in v:
            if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or x < 0 or x > hi:
                raise ValueError(f"{k} value out of range [0,{hi}]: {x}")

def synthetic_record(seed, pga_g, dur=8.0, dt=0.02):
    rng = random.Random(seed)
    fr = [rng.uniform(0.8, 6.0) for _ in range(10)]; ph = [rng.uniform(0, 6.283) for _ in range(10)]
    n = int(dur / dt); v = []
    for i in range(n):
        t = i * dt
        env = (t / 2.0) ** 2 if t < 2 else math.exp(-(t - 2) / 4.0)
        v.append(sum(math.sin(2*math.pi*f*t + p) for f, p in zip(fr, ph)) * env)
    pk = max(abs(x) for x in v)
    return [x / pk * pga_g * 9.81 for x in v], dt

def _section(tag, b, d, b0=None, d0=None):
    """Concrete b x d; steel stays at the ORIGINAL member size (b0 x d0). A jacket adds
    concrete only (same strength, perfect bond, no added bars)."""
    b0 = b0 or b; d0 = d0 or d
    ops.section("Fiber", tag)
    ops.patch("rect", 1, 8, 8, -b/2, -d/2, b/2, d/2)
    a = math.pi * (BAR/2)**2; y = d0/2 - COVER
    ops.layer("straight", 2, 3, a, -b0/2+COVER, -y, b0/2-COVER, -y)
    ops.layer("straight", 2, 3, a, -b0/2+COVER, y, b0/2-COVER, y)

def build(design):
    ops.wipe(); ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.uniaxialMaterial("Concrete01", 1, -FPC, -0.002, -0.2*FPC, -0.006)
    ops.uniaxialMaterial("Steel02", 2, FY, ES, 0.01, 18.5, 0.925, 0.15)
    ops.uniaxialMaterial("Steel01", 3, 355.0, ES, 0.01)
    ops.geomTransf("PDelta", 1)
    for s in range(3):
        t = design["jacket_mm"][s]; _section(10+s, COL_B+2*t, COL_D+2*t, COL_B, COL_D)
        ops.beamIntegration("Lobatto", 10+s, 10+s, 3)
    _section(20, BEAM_B, BEAM_D); ops.beamIntegration("Lobatto", 20, 20, 3)
    nodes = []; tag = 0; y = 0.0
    for f in range(4):
        row = []
        for l in range(NB+1):
            tag += 1; ops.node(tag, l*BAY, y); row.append(tag)
            if f > 0: ops.mass(tag, MASS_PER_FLOOR, MASS_PER_FLOOR, 1.0e6)
        nodes.append(row)
        if f < 3: y += H[f]
    for n in nodes[0]: ops.fix(n, 1, 1, 1)
    e = 0; beams = []
    for s in range(3):
        for l in range(NB+1):
            e += 1; ops.element("forceBeamColumn", e, nodes[s][l], nodes[s+1][l], 1, 10+s)
    for f in range(1, 4):
        for b in range(NB):
            e += 1; beams.append(e); ops.element("forceBeamColumn", e, nodes[f][b], nodes[f][b+1], 1, 20)
    for s in range(3):
        a = design["brace_mm2"][s]
        if a > 0:
            for (i, j) in ((nodes[s][0], nodes[s+1][1]), (nodes[s][1], nodes[s+1][0])):
                e += 1; ops.element("corotTruss", e, i, j, a, 3)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    for b in beams: ops.eleLoad("-ele", b, "-type", "-beamUniform", -GRAV)
    ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain")
    ops.test("NormDispIncr", 1e-6, 30); ops.algorithm("Newton")
    ops.integrator("LoadControl", 0.1); ops.analysis("Static")
    if ops.analyze(10) != 0: raise RuntimeError("gravity failed")
    ops.loadConst("-time", 0.0)
    return nodes

def run_record(design, rec, dt, nodes, sub=1):
    ops.timeSeries("Path", 5, "-dt", dt, "-values", *[a*1000.0 for a in rec])
    ops.pattern("UniformExcitation", 5, 1, "-accel", 5)
    ops.wipeAnalysis(); ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain")
    ops.test("NormDispIncr", 1e-4, 50)
    w = ops.eigen("-fullGenLapack", 2); w1, w2 = (2*math.pi/math.sqrt(x) for x in w[:2]); wa, wb = 2*math.pi/w1, 2*math.pi/w2
    z = 0.05; ops.rayleigh(2*z*wa*wb/(wa+wb), 2*z/(wa+wb), 0, 0)
    ops.integrator("Newmark", 0.5, 0.25); ops.algorithm("Newton"); ops.analysis("Transient")
    drift = acc = 0.0; steps = 0
    dts = dt / sub
    for i in range((len(rec) - 1) * sub):
        dtc, ok = dts, False
        for _ in range(3):
            if ops.analyze(1, dtc) == 0: ok = True; break
            ops.algorithm("NewtonLineSearch")
            if ops.analyze(1, dtc) == 0: ok = True; ops.algorithm("Newton"); break
            ops.algorithm("Newton"); dtc /= 2
            if ops.analyze(2, dtc) == 0: ok = True; break
        if not ok: return {"converged": False, "drift": float("inf"), "acc": float("inf"), "T1": w1}
        tnow = ops.getTime(); k = min(int(tnow / dt), len(rec) - 2); fr = tnow / dt - k
        ag = rec[k] * (1 - fr) + rec[k + 1] * fr          # ground accel, m/s^2 (Path series is linear)
        for s in range(3):
            for l in range(NB + 1):
                d = abs(ops.nodeDisp(nodes[s+1][l], 1) - ops.nodeDisp(nodes[s][l], 1)) / H[s]
                drift = max(drift, d)
        for f in range(1, 4):
            for l in range(NB + 1):   # ABSOLUTE floor accel = relative (mm/s^2 -> m/s^2) + ground
                acc = max(acc, abs(ops.nodeAccel(nodes[f][l], 1) / 1000.0 + ag))
    if not (math.isfinite(drift) and math.isfinite(acc)):
        return {"converged": False, "drift": float("inf"), "acc": float("inf"), "T1": w1}
    pga = max(abs(a) for a in rec)
    return {"converged": True, "drift": drift, "acc": acc, "acc_over_pga": acc / pga, "T1": w1}

def _ramp(x, good, bad):
    return max(0.0, min(1.0, (bad - x) / (bad - good)))

def record_score(m):
    if not m["converged"] or not all(math.isfinite(m[k]) for k in ("drift", "acc_over_pga")): return 0.0
    return 0.7 * _ramp(m["drift"], DRIFT_TARGET, DRIFT_LIMIT) + 0.3 * _ramp(m["acc_over_pga"], ACC_TARGET, ACC_LIMIT)

PUBLIC_SUITE = [(101, 0.25), (102, 0.4), (103, 0.5)]
SCORING_SUITE = [(201, 0.3), (202, 0.45), (203, 0.55), (204, 0.6)]

def evaluate(design, suite=None, sub=1):
    validate(design)
    c = cost(design)
    if c > BUDGET: return {"score": 0.0, "cost": c, "gate": "over_budget", "records": []}
    suite = suite or SCORING_SUITE
    nodes_per = []; recs = []
    for seed, pga in suite:
        nodes = build(design)
        rec, dt = synthetic_record(seed, pga)
        m = run_record(design, rec, dt, nodes, sub); m.update(seed=seed, pga=pga); m["score"] = record_score(m)
        recs.append(m)
    return {"score": min(r["score"] for r in recs), "cost": c, "gate": "ok", "records": recs}

def load_design(path):
    def bad(c): raise ValueError("non-finite JSON constant: " + c)
    d = json.loads(open(path, encoding="utf-8").read(200_000), parse_constant=bad)
    if not isinstance(d, dict): raise ValueError("design must be a JSON object")
    return d

def evaluate_file(path, suite_name="scoring", sub=1):
    """Never raises on a bad submission: returns {"score": 0, "error": ...} so callers get structured output."""
    try:
        d = load_design(path)
        r = evaluate(d, PUBLIC_SUITE if suite_name == "public" else SCORING_SUITE, sub)
    except (ValueError, OSError, UnicodeDecodeError, RuntimeError) as e:
        return {"score": 0.0, "error": f"{type(e).__name__}: {e}", "records": []}
    r["error"] = None; return r

if __name__ == "__main__":
    import argparse, time
    ap = argparse.ArgumentParser(prog="python -m retrofit.evaluator", description="Score a retrofit design JSON. Prints one JSON object (schema: retrofit/result.schema.json). Exit 0 = scored, 2 = invalid submission.")
    ap.add_argument("design"); ap.add_argument("--suite", choices=["scoring", "public"], default="scoring")
    ap.add_argument("--substeps", type=int, default=1, help="analysis substeps per record sample (timestep refinement)")
    a = ap.parse_args(); t = time.time()
    r = evaluate_file(a.design, a.suite, a.substeps); r["seconds"] = round(time.time() - t, 1)
    print("RESULT_JSON " + json.dumps(r, default=str)); raise SystemExit(2 if r["error"] else 0)
