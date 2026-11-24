"""Accuracy (% cables correctly matched) over cable count, one line per mode.

Reads every bench/results/*/summary.csv, pools all valid puzzles of the same cable count
(correct / total over all puzzles), and writes bench/results/accuracy_by_cables.png.
Excluded runs (refusals, leaks, runs without an answer) are listed in the footnote.

    python bench/plot_accuracy.py
"""
import csv
import glob
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

# (results folder prefix, item id, mode) -> reason; known invalid runs
EXCLUDE = {
    ("gpt-6.2-sol_high_20261124_083235", "bomb_n20_4220", "forbidden"): "refused (bomb theme)",
    ("gpt-6.2-sol_high_20261124_083235", "bomb_n40_4241", "forbidden"): "refused (bomb theme)",
    ("items_hard_gpt-6.2-sol_high_20261124_111432", "railway_hard_n40_543", "code"): "seed leak via folder name",
}
MODES = [("toolless", "No tools", "#2a78d6", "o"),
         ("forbidden", "Tools forbidden by prompt", "#eb6834", "s"),
         ("code", "Python allowed", "#1baf7a", "D")]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def load():
    pooled = defaultdict(lambda: [0, 0])      # (mode, n) -> [correct, total]
    points = defaultdict(list)                # (mode, n) -> per-puzzle accuracy
    excluded = []
    for path in sorted(glob.glob(os.path.join(RES, "*", "summary.csv"))):
        run = os.path.basename(os.path.dirname(path))
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (run, r["id"], r["mode"])
                reason = EXCLUDE.get(key)
                if not reason and str(r.get("refused", "")).lower() == "true":
                    reason = "refused"
                if not reason and str(r.get("timed_out", "")).lower() == "true":
                    reason = "timed out"
                if not reason and not r.get("seconds"):
                    reason = "no answer"
                if reason:
                    excluded.append(f"{r['id']} {r['mode']}: {reason}")
                    continue
                n, c, t = int(r["n_cables"]), int(r["correct"]), int(r["total"])
                pooled[(r["mode"], n)][0] += c
                pooled[(r["mode"], n)][1] += t
                points[(r["mode"], n)].append(100 * c / t)
    return pooled, points, excluded


def main():
    pooled, points, excluded = load()
    ns = sorted({n for (_, n) in pooled})
    xpos = {n: i for i, n in enumerate(ns)}   # even spacing, the counts are categories

    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 11})
    fig, ax = plt.subplots(figsize=(10, 6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ends = []                                 # [label_y, x, y, text]
    for mi, (mode, label, color, marker) in enumerate(MODES):
        off = (mi - 1) * 0.08                 # small dodge so per-puzzle dots do not overlap
        xs, ys = [], []
        for n in ns:
            if (mode, n) not in pooled:
                continue
            c, t = pooled[(mode, n)]
            xs.append(xpos[n] + off)
            ys.append(100 * c / t)
            for p in points[(mode, n)]:
                ax.scatter(xpos[n] + off, p, s=14, color=color, alpha=0.28, linewidths=0, zorder=2)
        ax.plot(xs, ys, color=color, lw=2, zorder=3)
        ax.scatter(xs, ys, s=64, color=color, marker=marker, edgecolors=SURFACE, linewidths=2,
                   zorder=4, label=label)
        ends.append([ys[-1], xs[-1], ys[-1], f"{label}  {ys[-1]:.0f}%"])

    # end labels: push apart so they never overlap (min gap 5 percentage points)
    ends.sort(key=lambda e: -e[0])
    for i in range(1, len(ends)):
        ends[i][0] = min(ends[i][0], ends[i - 1][0] - 5)
    for ly, x, y, text in ends:
        ax.annotate(text, (x, y), xytext=(x + 0.12, ly), textcoords="data", va="center",
                    color=INK, fontsize=10)

    def count_label(n):
        c = sorted({len(points[(m, n)]) for m, *_ in MODES if (m, n) in points})
        k = f"{c[0]}" if len(c) == 1 else f"{c[0]}-{c[-1]}"
        return f"{n}\n({k} puzzle{'' if k == '1' else 's'})"

    ax.set_xticks(range(len(ns)))
    ax.set_xticklabels([count_label(n) for n in ns], color=INK2)
    ax.set_xlim(-0.4, len(ns) - 1 + 1.9)
    ax.set_ylim(0, 104)
    ax.set_yticks(range(0, 101, 20))
    ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)], color=INK2)
    ax.set_xlabel("Number of cables", color=INK2)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    ax.legend(loc="lower left", frameon=False, labelcolor=INK)

    fig.suptitle("cablebench: gpt-6.2-sol (high), cables matched correctly", x=0.06, ha="left",
                 color=INK, fontsize=15, fontweight="semibold")
    ax.set_title("Large markers: all valid puzzles of that size pooled. Small dots: single puzzles.",
                 loc="left", color=INK2, fontsize=10)
    note = "Excluded: " + ("; ".join(excluded) if excluded else "none")
    fig.text(0.06, 0.015, note, color=INK2, fontsize=8, wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = os.path.join(RES, "accuracy_by_cables.png")
    fig.savefig(out, facecolor=SURFACE)
    print(out)
    for n in ns:
        print(n, {m: (f"{pooled[(m, n)][0]}/{pooled[(m, n)][1]}" if (m, n) in pooled else "-")
                  for m, *_ in MODES})


if __name__ == "__main__":
    main()
