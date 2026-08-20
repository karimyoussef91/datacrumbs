#!/usr/bin/env python3
"""Analyze a DataCrumbs IOR trace and prepare defensible roofline points.

The default trace is the two-rank POSIX IOR run generated on this node. A
compute roofline point requires FLOPs, bytes, and a wall-clock duration for each
layer. DataCrumbs syscall-only traces provide POSIX call timing but do not carry
byte-count arguments or MPI-IO events, so this tool never invents those values.
"""

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE = Path(
    "/home/cc/traces/26/08/20/"
    "trace-cc-mpi-ior-2rank-linked-xio-rooflines-ior-mpi-syscalls.pfw.gz"
)
DATA = ROOT / "data"
DEFAULT_IOR_PHASE_BYTES = 16 * 1024 * 1024
DEFAULT_IOR_WRITE_SECONDS = 0.050916
DEFAULT_IOR_READ_SECONDS = 0.002455


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help="DataCrumbs .pfw.gz trace")
    parser.add_argument("--application-flops", type=float, help="Application floating-point operations")
    parser.add_argument("--workload-bytes", type=float, help="Bytes transferred by the workload")
    parser.add_argument("--application-seconds", type=float, help="End-to-end application wall time")
    parser.add_argument("--mpiio-seconds", type=float, help="MPI-IO layer wall time from MPI-IO instrumentation")
    parser.add_argument(
        "--posix-seconds",
        type=float,
        help="POSIX layer wall time; default is the sum of observed POSIX syscall durations",
    )
    parser.add_argument(
        "--ior-write-bytes",
        type=float,
        help="Bytes written by IOR; defaults to the known 16 MiB phase in the bundled trace.",
    )
    parser.add_argument(
        "--ior-read-bytes",
        type=float,
        help="Bytes read by IOR; defaults to the known 16 MiB phase in the bundled trace.",
    )
    parser.add_argument(
        "--ior-write-seconds",
        type=float,
        help="IOR write wall time; defaults to the recorded bundled-trace phase time.",
    )
    parser.add_argument(
        "--ior-read-seconds",
        type=float,
        help="IOR read wall time; defaults to the recorded bundled-trace phase time.",
    )
    return parser.parse_args()


def load_trace(trace_path):
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        events = json.load(stream)
    if not isinstance(events, list):
        raise ValueError("expected a Chrome/Perfetto JSON event array")
    return events


def trace_summary(events):
    io_names = {"openat", "read", "write", "close", "fsync"}
    relevant = [event for event in events if event.get("name") in io_names and event.get("ph") == "X"]
    counts = Counter(event.get("name") for event in relevant)
    cumulative_seconds = sum(float(event.get("dur", 0.0)) for event in relevant) / 1.0e6
    by_pid = defaultdict(int)
    for event in relevant:
        by_pid[event.get("pid")] += 1
    return {
        "event_count": len(relevant),
        "counts": dict(sorted(counts.items())),
        "cumulative_posix_seconds": cumulative_seconds,
        "processes": dict(sorted(by_pid.items(), key=lambda item: str(item[0]))),
        "has_mpiio_events": any("mpi" in str(event.get("cat", "")).lower() for event in events),
        "has_byte_arguments": any(bool(event.get("args")) for event in relevant),
    }


def write_layer_report(summary, output_path):
    layers = [
        {
            "layer": "overall_application",
            "observed": "no",
            "reason": "Syscall trace has no application FLOP count or application wall-clock interval.",
        },
        {
            "layer": "mpi_io",
            "observed": "yes" if summary["has_mpiio_events"] else "no",
            "reason": (
                "MPI events appear in the trace."
                if summary["has_mpiio_events"]
                else "Current workload used IOR -a POSIX and this trace contains no MPI-IO events."
            ),
        },
        {
            "layer": "posix",
            "observed": "yes",
            "reason": (
                "POSIX events are present, but their args are empty; bytes must come from workload metadata."
                if not summary["has_byte_arguments"]
                else "POSIX events and arguments are present."
            ),
        },
    ]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["layer", "observed", "reason"])
        writer.writeheader()
        writer.writerows(layers)


def write_roofline_points(args, summary, output_path):
    rows = []
    flops = args.application_flops
    bytes_transferred = args.workload_bytes
    posix_seconds = args.posix_seconds if args.posix_seconds is not None else summary["cumulative_posix_seconds"]
    candidates = [
        ("overall_application", args.application_seconds, True),
        ("mpi_io", args.mpiio_seconds, summary["has_mpiio_events"]),
        ("posix", posix_seconds, True),
    ]
    for layer, duration, observed in candidates:
        if not observed or flops is None or bytes_transferred is None or duration is None:
            continue
        if flops <= 0.0 or bytes_transferred <= 0.0 or duration <= 0.0:
            continue
        rows.append(
            {
                "layer": layer,
                "operational_intensity": f"{flops / bytes_transferred:.12g}",
                "performance_gflops": f"{flops / duration / 1.0e9:.12g}",
                "duration_seconds": f"{duration:.12g}",
                "bytes": f"{bytes_transferred:.12g}",
                "flops": f"{flops:.12g}",
            }
        )
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        fields = ["layer", "operational_intensity", "performance_gflops", "duration_seconds", "bytes", "flops"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows

def default_ior_metadata(args):
    """Return recorded phase data only for the known local two-rank trace."""
    if args.trace.resolve() != DEFAULT_TRACE.resolve():
        return None
    return {
        "write_bytes": DEFAULT_IOR_PHASE_BYTES,
        "read_bytes": DEFAULT_IOR_PHASE_BYTES,
        "write_seconds": DEFAULT_IOR_WRITE_SECONDS,
        "read_seconds": DEFAULT_IOR_READ_SECONDS,
        "source": "IOR output recorded for the default two-rank POSIX trace",
    }

def write_io_layer_points(args, summary, output_path):
    defaults = default_ior_metadata(args) or {}
    write_bytes = args.ior_write_bytes if args.ior_write_bytes is not None else defaults.get("write_bytes")
    read_bytes = args.ior_read_bytes if args.ior_read_bytes is not None else defaults.get("read_bytes")
    write_seconds = args.ior_write_seconds if args.ior_write_seconds is not None else defaults.get("write_seconds")
    read_seconds = args.ior_read_seconds if args.ior_read_seconds is not None else defaults.get("read_seconds")
    rows = []
    if all(value is not None and value > 0.0 for value in (write_bytes, read_bytes, write_seconds, read_seconds)):
        total_bytes = write_bytes + read_bytes
        application_seconds = write_seconds + read_seconds
        source = defaults.get("source", "CLI-provided IOR phase metadata")
        rows.append(
            {
                "layer": "ior_application",
                "effective_bandwidth_gbs": f"{total_bytes / application_seconds / 1.0e9:.12g}",
                "bytes": f"{total_bytes:.12g}",
                "duration_seconds": f"{application_seconds:.12g}",
                "semantics": source,
            }
        )
        if summary["cumulative_posix_seconds"] > 0.0:
            rows.append(
                {
                    "layer": "posix_cumulative",
                    "effective_bandwidth_gbs": f"{total_bytes / summary['cumulative_posix_seconds'] / 1.0e9:.12g}",
                    "bytes": f"{total_bytes:.12g}",
                    "duration_seconds": f"{summary['cumulative_posix_seconds']:.12g}",
                    "semantics": "Workload bytes divided by summed traced POSIX syscall durations; includes concurrent thread-time and startup calls.",
                }
            )
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        fields = ["layer", "effective_bandwidth_gbs", "bytes", "duration_seconds", "semantics"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    args = parse_arguments()
    if not args.trace.is_file():
        raise SystemExit(f"trace not found: {args.trace}")
    DATA.mkdir(exist_ok=True)
    summary = trace_summary(load_trace(args.trace))
    analysis_path = DATA / "ior_trace_analysis.json"
    report_path = DATA / "ior_trace_layers.csv"
    points_path = DATA / "ior_roofline_points.csv"
    io_points_path = DATA / "ior_io_layer_points.csv"
    analysis_path.write_text(
        json.dumps({"trace": str(args.trace), **summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_layer_report(summary, report_path)
    points = write_roofline_points(args, summary, points_path)
    io_points = write_io_layer_points(args, summary, io_points_path)
    print(f"trace={args.trace}")
    print(f"posix_events={summary['event_count']}")
    print(f"posix_cumulative_seconds={summary['cumulative_posix_seconds']:.6f}")
    print(f"layer_report={report_path}")
    print(f"roofline_points={points_path}")
    print(f"io_layer_points={io_points_path}")
    print(f"plottable_points={len(points)}")
    print(f"io_layer_points_count={len(io_points)}")
    if not points:
        print(
            "No FLOP roofline points emitted: supply --application-flops, --workload-bytes, "
            "and layer wall times. MPI-IO also requires an IOR -a MPIIO trace with MPI instrumentation."
        )


if __name__ == "__main__":
    main()