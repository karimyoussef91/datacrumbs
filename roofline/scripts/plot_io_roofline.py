#!/usr/bin/env python3
"""Plot the I/O roofline (IOPS vs. I/O operational intensity).

Follows Zhu & Neuwirth (ICPADS'23): Attainable Performance = min(psi, kappa * IOI),
where psi is peak IOPS and kappa is peak I/O bandwidth (bytes/s).
"""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LAYER_COLORS = {
    "posix": "#9b2226",
    "overall_application": "#6f2dbd",
    "mpi_io": "#1f7a1f",
    "mpi_comm": "#0a6ebd",
    "memory": "#c9781f",
}


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--system-csv",
        type=Path,
        default=DATA / "io_roofline_system.csv",
        help="CSV from run_io_roofline_benchmark.sh with peak_iops and peak_bandwidth.",
    )
    parser.add_argument(
        "--points",
        type=Path,
        default=None,
        help="Optional CSV from analyze_io_roofline.py to overlay application/POSIX points.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output PNG path.")
    return parser.parse_args()


def metrics(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


def main():
    args = parse_arguments()
    system = metrics(args.system_csv)
    peak_iops = float(system["peak_iops"]["value"])
    peak_bandwidth_gbs = float(system["peak_bandwidth"]["value"])
    peak_bandwidth_bytes = peak_bandwidth_gbs * 1.0e9
    ridge_ioi = peak_iops / peak_bandwidth_bytes

    ioi = np.logspace(-9, -1, 800)
    fig, axis = plt.subplots(figsize=(9.5, 6.5), constrained_layout=True)

    axis.loglog(
        ioi,
        ioi * peak_bandwidth_bytes,
        label=f"Peak I/O bandwidth: {peak_bandwidth_gbs:.4f} GB/s",
        color="#007c91",
        linewidth=2.2,
    )
    axis.axhline(peak_iops, label=f"Peak IOPS: {peak_iops:.1f} IOP/s", color="#232323", linewidth=2.4)
    axis.scatter([ridge_ioi], [peak_iops], color="#232323", zorder=5, label=f"Ridge point: {ridge_ioi:.3e} IOP/byte")

    if args.points is not None and args.points.is_file():
        with args.points.open(newline="", encoding="utf-8") as stream:
            points = list(csv.DictReader(stream))
        for point in points:
            ioi_value = float(point["ioi"])
            iops_value = float(point["iops"])
            if ioi_value > 0.0 and iops_value > 0.0:
                label = point["layer"].replace("_", " ")
                axis.scatter(
                    [ioi_value],
                    [iops_value],
                    s=90,
                    marker="o",
                    color=LAYER_COLORS.get(point["layer"], "#333333"),
                    edgecolor="white",
                    linewidth=1.1,
                    zorder=6,
                    label=f"Trace point: {label}",
                )

    axis.set_title("I/O Roofline Model")
    axis.set_xlabel("I/O operational intensity [IOP/byte]")
    axis.set_ylabel("Attainable performance [IOPS]")
    axis.set_xlim(ioi[0], ioi[-1])
    axis.set_ylim(1e-1, peak_iops * 3)
    axis.grid(True, which="both", color="#d6d6d6", linewidth=0.6)
    axis.legend(loc="lower right", frameon=True, fontsize=9)
    fig.savefig(args.output, dpi=180)
    print(f"plot={args.output}")


if __name__ == "__main__":
    main()
