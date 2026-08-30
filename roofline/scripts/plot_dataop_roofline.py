#!/usr/bin/env python3
"""Plot a memory and I/O Data-Operation Roofline with trace points."""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESOURCE_STYLES = {
    "memory": ("#007c91", "-"),
    "io": ("#9b2226", "--"),
}
POINT_STYLES = {
    "memory": ("#007c91", "s"),
    "mpi_io": ("#2f7d32", "^"),
    "posix_io": ("#9b2226", "o"),
}


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ceilings",
        type=Path,
        default=DATA / "dataop_memory_io_ceilings.csv",
    )
    parser.add_argument(
        "--points",
        type=Path,
        default=DATA / "dataop_memory_io_points_dftracer.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dataop_memory_io_roofline.png",
    )
    return parser.parse_args()


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    args = parse_arguments()
    ceiling_rows = read_rows(args.ceilings)
    point_rows = read_rows(args.points) if args.points.is_file() else []
    if {row["resource"] for row in ceiling_rows} != set(RESOURCE_STYLES):
        raise SystemExit("ceilings CSV must contain exactly memory and io resources")

    dataops_peaks = {float(row["dataops_peak_per_second"]) for row in ceiling_rows}
    if len(dataops_peaks) != 1:
        raise SystemExit("all ceiling rows must use the same dataops_peak_per_second")
    dataops_peak = dataops_peaks.pop()
    effective = {
        row["resource"]: float(row["effective_bandwidth_bytes_per_second"])
        for row in ceiling_rows
    }

    point_x = [float(row["data_intensity_dataops_per_byte"]) for row in point_rows]
    positive_x = [value for value in point_x if value > 0.0]
    knees = [dataops_peak / bandwidth for bandwidth in effective.values()]
    anchors = positive_x + knees
    x_min = min(anchors) / 100.0
    x_max = max(anchors) * 100.0
    intensity = np.logspace(np.log10(x_min), np.log10(x_max), 800)

    fig, axis = plt.subplots(figsize=(10.5, 7), constrained_layout=True)
    resource_rates = []
    for row in ceiling_rows:
        resource = row["resource"]
        color, linestyle = RESOURCE_STYLES[resource]
        amplification = float(row["traffic_amplification"])
        effective_gbs = effective[resource] / 1.0e9
        ceiling_kind = row.get("ceiling_kind", "measured_traffic_amplification")
        bandwidth_label = "raw reference" if ceiling_kind == "assumed_unity_raw_reference" else "effective"
        rates = effective[resource] * intensity
        resource_rates.append(rates)
        axis.loglog(
            intensity,
            rates,
            color=color,
            linestyle=linestyle,
            linewidth=2.0,
            label=f"{resource}: {effective_gbs:.3g} GB/s {bandwidth_label} (alpha={amplification:.3g})",
        )

    peak_semantics = ceiling_rows[0].get("dataops_peak_semantics", "")
    peak_label = "Provisional POSIX IOPS reference" if peak_semantics.startswith("provisional") else "DataOp ceiling"
    axis.axhline(dataops_peak, color="#232323", linewidth=2.3, label=f"{peak_label}: {dataops_peak:.3g}/s")
    envelope = np.minimum(dataops_peak, np.minimum.reduce(resource_rates))
    axis.loglog(intensity, envelope, color="#232323", linewidth=3.0, alpha=0.65, label="Active lower envelope")

    for row in point_rows:
        x_value = float(row["data_intensity_dataops_per_byte"])
        y_value = float(row["dataop_rate_per_second"])
        if x_value <= 0.0 or y_value <= 0.0:
            continue
        color, marker = POINT_STYLES.get(row["point"], ("#555555", "o"))
        axis.scatter(
            [x_value],
            [y_value],
            s=100,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=1.0,
            zorder=6,
            label=f"Trace point: {row['point'].replace('_', ' ')}",
        )

    y_candidates = [dataops_peak, *(float(row["dataop_rate_per_second"]) for row in point_rows)]
    axis.set_xlim(x_min, x_max)
    axis.set_ylim(max(min(y_candidates) / 100.0, 1.0e-6), max(y_candidates) * 10.0)
    axis.set_title("Memory and I/O Data-Operation Roofline")
    axis.set_xlabel("Data Intensity [logical DataOps / logical byte]")
    axis.set_ylabel("Data Operation Rate [logical DataOps / s]")
    axis.grid(True, which="both", color="#d6d6d6", linewidth=0.6)
    axis.legend(loc="best", frameon=True, fontsize=8.5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    print(f"plot={args.output}")


if __name__ == "__main__":
    main()