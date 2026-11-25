"""Independent checks of the OpenSees pieces the scorer relies on. Each returns (measured, expected, rel_err)."""
import math
import openseespy.opensees as ops
from . import evaluator as E

def _cantilever(E_=200000.0, I=1.0e8, L=3000.0, elastic=True):
    ops.wipe(); ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.node(1, 0.0, 0.0); ops.node(2, 0.0, L); ops.fix(1, 1, 1, 1); ops.geomTransf("Linear", 1)
    ops.element("elasticBeamColumn", 1, 1, 2, 1.0e4, E_, I, 1)

def cantilever_deflection(E_=200000.0, I=1.0e8, L=3000.0, P=10000.0):
    _cantilever(E_, I, L); ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1); ops.load(2, P, 0.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain"); ops.test("NormDispIncr", 1e-10, 10)
    ops.algorithm("Newton"); ops.integrator("LoadControl", 1.0); ops.analysis("Static"); assert ops.analyze(1) == 0
    want = P * L**3 / (3 * E_ * I); got = ops.nodeDisp(2, 1); return got, want, abs(got - want) / want

def sdof_period(E_=200000.0, I=1.0e8, L=3000.0, m=5000.0):
    _cantilever(E_, I, L); ops.mass(2, m, m, 1.0e6)
    lam = ops.eigen("-fullGenLapack", 3); lam = [x for x in lam if x > 0]
    got = 2 * math.pi / math.sqrt(min(lam)); want = 2 * math.pi * math.sqrt(m / (3 * E_ * I / L**3))
    return got, want, abs(got - want) / want

def column_pushover_checks(L=1500.0, drift=0.04, hardening=0.01):
    """Nonlinear fiber column pushed to 4% drift at zero axial load. Checks (a) base moment >= the plastic couple
    M_p = As*fy*(layer spacing) (strain hardening adds to it, so this is a lower bound, not an exact value) and
    (b) base reaction moment equals the base-section moment (equilibrium). KNOWN GAP: no independent check of
    the concrete law or cyclic hysteresis; an attempted hand fiber integration did not match because Concrete01 is history dependent."""
    ops.wipe(); ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.uniaxialMaterial("Concrete01", 1, -E.FPC, -0.002, -0.2 * E.FPC, -0.006)
    ops.uniaxialMaterial("Steel02", 2, E.FY, E.ES, hardening, 18.5, 0.925, 0.15)
    E._section(1, E.COL_B, E.COL_D); ops.beamIntegration("Lobatto", 1, 1, 5); ops.geomTransf("Linear", 1)
    ops.node(1, 0.0, 0.0); ops.node(2, 0.0, L); ops.fix(1, 1, 1, 1)
    ops.element("forceBeamColumn", 1, 1, 2, 1, 1)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1); ops.load(2, 1.0, 0.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain"); ops.test("NormDispIncr", 1e-6, 50)
    ops.algorithm("Newton"); n = 200; ops.integrator("DisplacementControl", 2, 1, drift * L / n); ops.analysis("Static")
    for _ in range(n):
        if ops.analyze(1) != 0: raise RuntimeError("pushover did not converge")
    ops.reactions(); M = abs(ops.nodeReaction(1, 3))
    Mp = 3 * math.pi * (E.BAR / 2) ** 2 * E.FY * (E.COL_D - 2 * E.COVER)
    Mf = ops.eleResponse(1, "section", 1, "force")[1]
    return {"base_moment": M, "Mp": Mp, "above_Mp": (M - Mp) / Mp, "equilibrium_err": abs(M - abs(Mf)) / M}

def _rk4_peak(rec, dt, omega, zeta, sub=10):
    """Independent solution of u'' + 2 z w u' + w^2 u = -ag(t), ag linear between samples (RK4)."""
    h = dt / sub; u = v = 0.0; peak = 0.0
    def a(t, u, v):
        k = min(int(t / dt), len(rec) - 2); f = t / dt - k
        return -(rec[k] * (1 - f) + rec[k + 1] * f) - 2 * zeta * omega * v - omega**2 * u
    for i in range((len(rec) - 1) * sub):
        t = i * h
        k1u, k1v = v, a(t, u, v); k2u, k2v = v + h/2*k1v, a(t + h/2, u + h/2*k1u, v + h/2*k1v)
        k3u, k3v = v + h/2*k2v, a(t + h/2, u + h/2*k2u, v + h/2*k2v); k4u, k4v = v + h*k3v, a(t + h, u + h*k3u, v + h*k3v)
        u += h/6*(k1u + 2*k2u + 2*k3u + k4u); v += h/6*(k1v + 2*k2v + 2*k3v + k4v); peak = max(peak, abs(u))
    return peak

def sdof_time_history(seed=101, pga_g=0.3, zeta=0.05, m=5000.0, sub=4):
    """OpenSees Newmark (average acceleration) transient analysis of an elastic SDOF vs an independent RK4 solve."""
    rec, dt = E.synthetic_record(seed, pga_g)
    _cantilever(); ops.mass(2, m, m, 1.0e6)
    omega = math.sqrt(3 * 200000.0 * 1.0e8 / 3000.0**3 / m)
    ops.timeSeries("Path", 1, "-dt", dt, "-values", *[x * 1000.0 for x in rec]); ops.pattern("UniformExcitation", 1, 1, "-accel", 1)
    ops.rayleigh(2 * zeta * omega, 0.0, 0.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain"); ops.test("NormDispIncr", 1e-10, 20)
    ops.algorithm("Newton"); ops.integrator("Newmark", 0.5, 0.25); ops.analysis("Transient")
    peak = 0.0
    for _ in range((len(rec) - 1) * sub):
        assert ops.analyze(1, dt / sub) == 0; peak = max(peak, abs(ops.nodeDisp(2, 1)))
    want = _rk4_peak(rec, dt, omega, zeta) * 1000.0   # m -> mm (record is m/s^2, OpenSees model is N-mm-s)
    return peak, want, abs(peak - want) / want

def frame_gravity_equilibrium():
    d = {"jacket_mm": [20.0] * 3, "brace_mm2": [500.0] * 3}; nodes = E.build(d); ops.reactions()
    got = sum(ops.nodeReaction(n, 2) for n in nodes[0]); want = E.GRAV * E.BAY * E.NB * 3
    return got, want, abs(got - want) / want

CHECKS = {"cantilever_deflection": (cantilever_deflection, 1e-6), "sdof_period": (sdof_period, 1e-4),
          "sdof_time_history_vs_rk4": (sdof_time_history, 0.02), "gravity_equilibrium": (frame_gravity_equilibrium, 1e-6)}

if __name__ == "__main__":
    for n, (fn, tol) in CHECKS.items():
        g, w, e = fn(); print(f"[{'PASS' if e < tol else 'FAIL'}] {n}: measured {g:.6g} expected {w:.6g} err {e:.3%}")
    r0 = column_pushover_checks(hardening=0.0)
    print(f"[{'PASS' if abs(r0['above_Mp']) < 0.05 else 'FAIL'}] column, NO hardening (b=0): base moment {r0['base_moment']/1e6:.2f} kN m vs plastic couple Mp {r0['Mp']/1e6:.2f} kN m ({r0['above_Mp']:+.1%}, tolerance +-5%)")
    r = column_pushover_checks()
    print(f"[{'PASS' if r['above_Mp'] > r0['above_Mp'] else 'FAIL'}] column, b=1%: base moment {r['base_moment']/1e6:.2f} kN m ({r['above_Mp']:+.1%} vs Mp); hardening raises moment relative to b=0")
    print(f"[{'PASS' if r['equilibrium_err'] < 1e-4 else 'FAIL'}] base reaction vs base-section moment equilibrium err {r['equilibrium_err']:.2e}")
