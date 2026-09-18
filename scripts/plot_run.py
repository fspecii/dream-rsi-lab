"""Optional figure builder: uv run --with matplotlib python scripts/plot_run.py RUN_DIR."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = json.loads((args.directory / "results.json").read_text())
    pairs = result["holdouts"]
    fixed_color, dream_color = "#6d7884", "#16736b"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7), layout="constrained")
    xs = list(range(1, len(pairs) + 1))
    axes[0].bar([x - .18 for x in xs], [p["fixed"]["calls"] for p in pairs], width=.36, color=fixed_color, label="Fixed exploration")
    axes[0].bar([x + .18 for x in xs], [p["dream"]["calls"] for p in pairs], width=.36, color=dream_color, label="Replay-selected policy")
    axes[0].set(title="Fresh episodes: discovery work", xlabel="Paired seed", ylabel="Actual discovery-model calls", xticks=xs, ylim=(0, result["config"]["budget"] * 1.15))
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].scatter([x - .08 for x in xs], [p["fixed"]["best"] for p in pairs], color=fixed_color, marker="s", s=55)
    axes[1].scatter([x + .08 for x in xs], [p["dream"]["best"] for p in pairs], color=dream_color, marker="o", s=45)
    values = [p[arm]["best"] for p in pairs for arm in ("fixed", "dream")]
    axes[1].set(title="Fresh episodes: exact task score", xlabel="Paired seed", ylabel="Best sum–difference ratio (higher is better)", xticks=xs,
                ylim=(min(values) - .025, max(values) + .025))
    cycles = list(range(1, len(result["selections"]) + 1))
    for x, s in zip(cycles, result["selections"]):
        axes[2].plot([x-.05, x+.05], [s["before"], s["after"]], color="#c4cbd0", linewidth=2)
    axes[2].scatter([x-.05 for x in cycles], [s["before"] for s in result["selections"]], marker="s", color=fixed_color, label="Incumbent on current pool")
    axes[2].scatter([x+.05 for x in cycles], [s["after"] for s in result["selections"]], marker="o", color=dream_color, label="Selected on current pool")
    axes[2].set(title="Training: replay selection", xlabel="Recursive cycle (pool changes each cycle)", ylabel="Paper objective", xticks=cycles)
    axes[2].legend(frameon=False, fontsize=8)
    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle(f"Dream-RSI demonstration | {result['config']['model']} | {len(pairs)} fresh paired episodes", fontsize=14, fontweight="bold")
    figure = args.directory / "experiment.png"
    fig.savefig(figure, dpi=170)
    fig.savefig(args.directory / "experiment.svg")
    print(figure.resolve())


if __name__ == "__main__":
    main()
