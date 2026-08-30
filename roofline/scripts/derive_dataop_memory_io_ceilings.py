#!/usr/bin/env python3
"""Derive memory and I/O DataOp ceilings from existing benchmark CSVs.

The benchmark CSVs provide raw sustainable bandwidths. Optional measured
traffic volumes convert them to application-effective ceilings. Without those
volumes, alpha=1 is emitted explicitly as an unadjusted raw reference. The IOR
peak IOPS value is retained as a provisional operation-rate reference because
its POSIX-operation semantics differ from the logical MPI-IO DataOp.
"""

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-csv", type=Path, default=DATA / "memory.csv")
    parser.add_argument("--io-csv", type=Path, default=DATA / "io_roofline_system.csv")
    parser.add_argument("--logical-bytes", type=float, help="Logical bytes Q_D for amplification.")
    parser.add_argument("--memory-traffic-bytes", type=float, help="Measured memory traffic Q_M.")
    parser.add_argument("--io-traffic-bytes", type=float, help="Measured I/O traffic Q_IO.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA / "dataop_memory_io_ceilings.csv",
    )
    return parser.parse_args()


def read_metrics(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


def metric(metrics, name, expected_unit, source):
    if name not in metrics:
        raise SystemExit(f"missing metric {name!r} in {source}")
    row = metrics[name]
    if row["unit"] != expected_unit:
        raise SystemExit(
            f"unexpected unit for {name} in {source}: {row['unit']!r}; expected {expected_unit!r}"
        )
    value = float(row["value"])
    if value <= 0.0:
        raise SystemExit(f"{name} in {source} must be greater than zero")
    return value


def amplification(logical_bytes, traffic_bytes, resource):
    if traffic_bytes is None:
        return 1.0, "assumed_unity_raw_reference"
    if logical_bytes is None:
        raise SystemExit(f"--logical-bytes is required with --{resource}-traffic-bytes")
    if logical_bytes <= 0.0 or traffic_bytes <= 0.0:
        raise SystemExit("logical and resource traffic bytes must be greater than zero")
    return traffic_bytes / logical_bytes, "measured_traffic_amplification"


def main():
    args = parse_arguments()
    memory = read_metrics(args.memory_csv)
    io = read_metrics(args.io_csv)
    memory_bandwidth_gbs = metric(memory, "dram_bandwidth", "GB/s", args.memory_csv)
    io_bandwidth_gbs = metric(io, "peak_bandwidth", "GB/s", args.io_csv)
    provisional_peak = metric(io, "peak_iops", "IOP/s", args.io_csv)

    resources = (
        ("memory", memory_bandwidth_gbs, args.memory_traffic_bytes, args.memory_csv, "dram_bandwidth"),
        ("io", io_bandwidth_gbs, args.io_traffic_bytes, args.io_csv, "peak_bandwidth"),
    )
    rows = []
    for resource, bandwidth_gbs, traffic_bytes, source, source_metric in resources:
        alpha, ceiling_kind = amplification(args.logical_bytes, traffic_bytes, resource)
        raw_bandwidth = bandwidth_gbs * 1.0e9
        rows.append(
            {
                "resource": resource,
                "raw_bandwidth_bytes_per_second": f"{raw_bandwidth:.12g}",
                "logical_bytes": "" if args.logical_bytes is None else f"{args.logical_bytes:.12g}",
                "resource_traffic_bytes": "" if traffic_bytes is None else f"{traffic_bytes:.12g}",
                "traffic_amplification": f"{alpha:.12g}",
                "effective_bandwidth_bytes_per_second": f"{raw_bandwidth / alpha:.12g}",
                "dataops_peak_per_second": f"{provisional_peak:.12g}",
                "ceiling_kind": ceiling_kind,
                "bandwidth_source": str(source),
                "bandwidth_metric": source_metric,
                "dataops_peak_semantics": "provisional IOR peak POSIX IOPS; not a measured logical MPI-IO DataOp peak",
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
            f"{row['resource']}: raw_bandwidth_Bps={row['raw_bandwidth_bytes_per_second']} "
            f"alpha={row['traffic_amplification']} kind={row['ceiling_kind']}"
        )
    print(f"dataops_peak_reference={provisional_peak:.12g} semantics=provisional_POSIX_IOPS")


if __name__ == "__main__":
    main()