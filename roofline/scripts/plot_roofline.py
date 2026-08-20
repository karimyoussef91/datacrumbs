#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "roofline_model.png"


def parse_arguments():
    parser = argparse.ArgumentParser(description="Plot measured roofs and optional application points.")
    parser.add_argument(
        "--points",
        type=Path,
        default=DATA / "ior_roofline_points.csv",
        help="CSV created by analyze_ior_trace.py; empty files add no markers.",
    )
    parser.add_argument(
        "--io-layer-points",
        type=Path,
        default=DATA / "ior_io_layer_points.csv",
        help="I/O throughput points from analyze_ior_trace.py, rendered in a unit-correct inset.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Output PNG path")
    return parser.parse_args()


def metrics(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


args = parse_arguments()
cpu = metrics(DATA / "cpu.csv")
memory = metrics(DATA / "memory.csv")
storage = metrics(DATA / "storage.csv")
compute_peak = float(cpu["compute_peak"]["value"])
dram_bandwidth = float(memory["dram_bandwidth"]["value"])
read_bandwidth = float(storage["storage_read_bandwidth"]["value"])
write_bandwidth = float(storage["storage_write_bandwidth"]["value"])
storage_class = storage["storage_read_bandwidth"]["storage_class"]
model = storage["storage_read_bandwidth"]["model"] or storage["storage_read_bandwidth"]["device"]

intensity = np.logspace(-4, 3, 800)
fig, axis = plt.subplots(figsize=(11, 7), constrained_layout=True)

roofs = [
    (dram_bandwidth, "DRAM STREAM Triad", "#007c91", "-"),
    (read_bandwidth, f"{storage_class} sequential read", "#c43c39", "--"),
    (write_bandwidth, f"{storage_class} sequential write", "#d67a00", "--"),
]
for bandwidth, label, color, style in roofs:
    axis.loglog(intensity, intensity * bandwidth, label=f"{label}: {bandwidth:.2f} GB/s", color=color, linestyle=style, linewidth=2.2)

axis.axhline(compute_peak, label=f"Measured DP FMA peak: {compute_peak:.1f} GFLOP/s", color="#232323", linewidth=2.4)
for bandwidth, label, color, _ in roofs:
    knee = compute_peak / bandwidth
    if intensity[0] <= knee <= intensity[-1]:
        axis.scatter([knee], [compute_peak], color=color, zorder=5)

if args.points.is_file():
    with args.points.open(newline="", encoding="utf-8") as stream:
        points = list(csv.DictReader(stream))
    colors = {"overall_application": "#6f2dbd", "mpi_io": "#1f7a1f", "posix": "#9b2226"}
    for point in points:
        intensity_value = float(point["operational_intensity"])
        performance_value = float(point["performance_gflops"])
        if intensity_value > 0.0 and performance_value > 0.0:
            label = point["layer"].replace("_", " ")
            axis.scatter(
                [intensity_value],
                [performance_value],
                s=90,
                marker="o",
                color=colors.get(point["layer"], "#333333"),
                edgecolor="white",
                linewidth=1.1,
                zorder=6,
                label=f"Trace point: {label}",
            )

if args.io_layer_points.is_file():
    with args.io_layer_points.open(newline="", encoding="utf-8") as stream:
        io_points = list(csv.DictReader(stream))
    if io_points:
        inset = axis.inset_axes([0.20, 0.10, 0.31, 0.18])
        labels = [point["layer"].replace("_", " ") for point in io_points]
        bandwidths = [float(point["effective_bandwidth_gbs"]) for point in io_points]
        colors = ["#6f2dbd", "#9b2226"]
        positions = list(range(len(io_points)))
        inset.scatter(bandwidths, positions, s=65, color=colors[: len(io_points)], zorder=3)
        inset.set_xscale("log")
        inset.set_yticks(positions, labels=labels)
        inset.set_xlabel("effective I/O GB/s", fontsize=8)
        inset.set_title("IOR stack points", fontsize=9)
        inset.grid(True, axis="x", which="both", color="#d6d6d6", linewidth=0.5)
        inset.tick_params(axis="both", labelsize=8)

read_scale = read_bandwidth / dram_bandwidth
write_scale = write_bandwidth / dram_bandwidth
axis.text(
    0.00014,
    compute_peak * 0.7,
    f"Storage device: {model}\n"
    f"Read scaling: {read_scale:.4f} x DRAM\n"
    f"Write scaling: {write_scale:.4f} x DRAM",
    fontsize=10,
    bbox={"boxstyle": "square,pad=0.4", "facecolor": "white", "edgecolor": "#777777"},
)

axis.set_title("Measured Node Roofline: Compute, DRAM, and Storage", pad=14)
axis.set_xlabel("Operational intensity [FLOP/byte]")
axis.set_ylabel("Attainable performance [GFLOP/s]")
axis.set_xlim(intensity[0], intensity[-1])
axis.set_ylim(1e-2, compute_peak * 2)
axis.grid(True, which="both", color="#d6d6d6", linewidth=0.6)
axis.legend(loc="lower right", frameon=True)
fig.savefig(args.output, dpi=180)
print(f"plot={args.output}")