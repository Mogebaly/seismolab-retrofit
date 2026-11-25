"""Reference search: a small deterministic grid on the public scoring suite.
Braces are the cheap lever (see README), so the grid varies brace area per story profile and a
uniform jacket. It is a baseline, NOT a proven optimum: it only gives a lower bound on attainable score.
Usage: python -m retrofit.reference_search <part 0-3>   (parts split the grid for parallel runs)"""
import itertools, json, sys
from . import evaluator as E
JACKETS = [0.0, 30.0]
PROFILES = {"flat": (1, 1, 1), "bottom_heavy": (1.5, 1, 0.5), "top_light": (1, 1, 0.25), "bottom_light": (0.5, 1, 1)}
LEVELS = [1000.0, 2000.0]
def grid():
    for j, (pn, prof), lv in itertools.product(JACKETS, PROFILES.items(), LEVELS):
        yield {"jacket_mm": [j]*3, "brace_mm2": [min(E.BRACE_MAX, lv*m) for m in prof]}
if __name__ == "__main__":
    part = int(sys.argv[1]); out = []
    for i, d in enumerate(grid()):
        if i % 4 != part: continue
        r = E.evaluate(d); out.append({"design": d, "score": r["score"], "cost": r["cost"]})
    json.dump(out, open(f"retrofit/data/_grid{part}.json", "w"))
    print("DONE", part, len(out))
