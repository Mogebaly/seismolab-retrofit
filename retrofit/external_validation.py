"""External validation case: ELASTIC 2D 7-story, 2-bay frame from the OpenSeesPy documentation
(https://openseespydoc.readthedocs.io/en/latest/src/PortalFrame2d.html), which cites
SAP2000 Verification Manual (1997) Example 1 and SeismoStruct Verification Report v6 (2012) Example 11.
Reference values below are copied from that page's published comparison table (kip, in).

SCOPE: this checks OpenSees' elastic beam-column, rigid-floor (equalDOF) and eigen machinery against two other
programs. It says NOTHING about nonlinear fiber behavior, time-history analysis or the retrofit scorer."""
import math
import openseespy.opensees as ops

PERIODS_SAP2000 = [1.2732, 0.4313, 0.2420, 0.1602, 0.1190, 0.0951, 0.0795]   # s, published to 4 decimals
STATIC_SAP2000 = {"disp_top": 1.45076, "axial_bottom_left": 69.99, "moment_bottom_left": 2324.68}
W = {'W14X176': (51.7, 2150.), 'W14X211': (62.1, 2670.), 'W14X246': (72.3, 3230.), 'W14X287': (84.4, 3910.),
     'W24X110': (32.5, 3330.), 'W24X130': (38.3, 4020.), 'W24X160': (47.1, 5120.)}

def run():
    ops.wipe(); ops.model("Basic", "-ndm", 2)
    bay, heights, Emod, massX = 360.0, [162.0, 162.0, 156.0, 156.0, 156.0, 156.0, 156.0], 29500.0, 0.49
    beams = ['W24X160', 'W24X160', 'W24X130', 'W24X130', 'W24X110', 'W24X110', 'W24X110']
    ext = ['W14X246', 'W14X246', 'W14X246', 'W14X211', 'W14X211', 'W14X176', 'W14X176']
    inn = ['W14X287', 'W14X287', 'W14X287', 'W14X246', 'W14X246', 'W14X211', 'W14X211']
    cols = [ext, inn, ext]
    tag, y = 1, 0.0
    for j in range(8):
        for i in range(3): ops.node(tag, i * bay, y); tag += 1
        if j < 7: y += heights[j]
    for n in (1, 2, 3): ops.fix(n, 1, 1, 1)
    ref = 5
    for j in range(1, 8):
        for i in range(3):
            n = 3 * j + 1 + i
            if n != ref: ops.equalDOF(ref, n, 1)
            else: ops.mass(ref, massX, 1.0e-10, 1.0e-10)
        ref += 3
    ops.geomTransf("Linear", 1); e = 1
    for j in range(3):
        a, b = j + 1, j + 4
        for i in range(7):
            A, I = W[cols[j][i]]; ops.element("elasticBeamColumn", e, a, b, A, Emod, I, 1, "-mass", 0.0, "-lMass"); a = b; b += 3; e += 1
    for j in range(1, 8):
        a = 3 * j + 1; b = a + 1; A, I = W[beams[j - 1]]
        for i in range(2): ops.element("elasticBeamColumn", e, a, b, A, Emod, I, 1, "-mass", 0.0, "-lMass"); a = b; b += 1; e += 1
    lam = ops.eigen(7); periods = [2 * math.pi / math.sqrt(x) for x in lam]
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for n, f in ((22, 20.0), (19, 15.0), (16, 12.5), (13, 10.0), (10, 7.5), (7, 5.0), (4, 2.5)): ops.load(n, f, 0.0, 0.0)
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static"); assert ops.analyze(1) == 0
    f = ops.eleResponse(1, "forces")
    got = {"disp_top": ops.nodeDisp(22, 1), "axial_bottom_left": abs(f[1]), "moment_bottom_left": f[2]}
    return periods, got

if __name__ == "__main__":
    periods, got = run(); ok = True
    for i, (p, r) in enumerate(zip(periods, PERIODS_SAP2000)):
        good = abs(p - r) < 1e-4 + 1e-9; ok &= good
        print(f"[{'PASS' if good else 'FAIL'}] period {i+1}: OpenSees {p:.5f} s vs SAP2000 {r:.4f} s (|diff| {abs(p-r):.1e}, tol 1e-4 = published precision)")
    for k, r in STATIC_SAP2000.items():
        tol = {"disp_top": 1e-3, "axial_bottom_left": 1e-2, "moment_bottom_left": 1e-2}[k]; good = abs(got[k] - r) < tol; ok &= good
        print(f"[{'PASS' if good else 'FAIL'}] {k}: OpenSees {got[k]:.4f} vs SAP2000 {r} (tol {tol})")
    raise SystemExit(0 if ok else 1)
