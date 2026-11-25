"""Evaluate reference designs on the public scoring suite; write JSON + figure. Usage: python -m retrofit.make_results <out_json> [figure.png]"""
import json, sys
from . import evaluator as E

def main(out, fig_path=None):
    names = ("noop", "uniform", "targeted", "reference_search")
    designs = {n: E.load_design(f"retrofit/data/{n}.json") for n in names}
    res = {n: E.evaluate(d) for n, d in designs.items()}
    json.dump({"designs": designs, "results": res}, open(out, "w"), indent=1)
    for n in names:
        r = res[n]; print("SUM", n, round(r["score"], 4), round(r["cost"]), [(round(x["drift"]*100, 2), round(x["acc_over_pga"], 2), round(x["score"], 3)) for x in r["records"]])
    if fig_path:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.2)); w = 0.2; x = range(len(names))
        for k, (seed, pga) in enumerate(E.SCORING_SUITE):
            ax[0].bar([i + k*w for i in x], [res[n]["records"][k]["score"] for n in names], w, label=f"seed {seed}, PGA {pga}g")
            ax[1].bar([i + k*w for i in x], [res[n]["records"][k]["drift"]*100 for n in names], w)
            ax[2].bar([i + k*w for i in x], [res[n]["records"][k]["acc_over_pga"] for n in names], w)
        for a, t in zip(ax, ("Record score (1 = both targets met)", "Peak interstory drift (%)", "Peak absolute floor accel / PGA")):
            a.set_xticks([i + 1.5*w for i in x]); a.set_xticklabels(names, fontsize=8); a.set_title(t, fontsize=10)
        ax[1].axhline(E.DRIFT_TARGET*100, ls="--", c="k", lw=.8); ax[2].axhline(E.ACC_TARGET, ls="--", c="k", lw=.8)
        ax[0].legend(fontsize=7); fig.suptitle("Synthetic public records, public suite; dashed = target", fontsize=9); fig.tight_layout(); fig.savefig(fig_path, dpi=150)
if __name__ == "__main__": main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
