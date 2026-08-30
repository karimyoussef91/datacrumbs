#!/usr/bin/env python3
"""Generate measured effective ceilings for a Data-Operation Roofline.

Each memory or I/O ceiling is B_r / alpha_r, where alpha_r is measured
resource traffic divided by logical application bytes. Communication is
intentionally deferred, and no missing traffic is inferred.
"""

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logical-bytes", type=float, required=True, help="Logical application bytes Q_D.")
    parser.add_argument("--dataops-peak", type=float, required=True, help="Measured peak logical DataOps/s.")
    for resource in ("memory", "io"):
        parser.add_argument(
            f"--{resource}-bandwidth-gbs",
            type=float,
            required=True,
            help=f"Measured sustainable {resource} bandwidth in decimal GB/s.",
        )
        parser.add_argument(
            f"--{resource}-traffic-bytes",
            type=float,
            required=True,
            help=f"Measured physical bytes crossing the {resource} resource.",
        )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA / "dataop_memory_io_ceilings.csv",
        help="Output CSV consumed by plot_dataop_roofline.py.",
    )
    return parser.parse_args()


def positive(parser, name, value):
    if value <= 0.0:
        parser.error(f"{name} must be greater than zero")


def main():
    parser = argparse.ArgumentParser(add_help=False)
    args = parse_arguments()
    positive(parser, "--logical-bytes", args.logical_bytes)
    positive(parser, "--dataops-peak", args.dataops_peak)

    rows = []
    for resource in ("memory", "io"):
        bandwidth_gbs = getattr(args, f"{resource}_bandwidth_gbs")
        traffic_bytes = getattr(args, f"{resource}_traffic_bytes")
        positive(parser, f"--{resource}-bandwidth-gbs", bandwidth_gbs)
        positive(parser, f"--{resource}-traffic-bytes", traffic_bytes)
        amplification = traffic_bytes / args.logical_bytes
        raw_bandwidth = bandwidth_gbs * 1.0e9
        rows.append(
            {
                "resource": resource,
                "raw_bandwidth_bytes_per_second": f"{raw_bandwidth:.12g}",
                "logical_bytes": f"{args.logical_bytes:.12g}",
                "resource_traffic_bytes": f"{traffic_bytes:.12g}",
                "traffic_amplification": f"{amplification:.12g}",
                "effective_bandwidth_bytes_per_second": f"{raw_bandwidth / amplification:.12g}",
                "dataops_peak_per_second": f"{args.dataops_peak:.12g}",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"ceilings={args.output}")
    for row in rows:
        print(
            f"{row['resource']}: alpha={row['traffic_amplification']} "
            f"effective_bandwidth_Bps={row['effective_bandwidth_bytes_per_second']}"
        )


if __name__ == "__main__":
    main()