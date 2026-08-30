#!/usr/bin/env python3
"""Derive memory and I/O DataOp points with dftracer-utils.

The logical DataOp count W is either supplied explicitly or counted from the
declared --dataop-events. Each point uses the same W and logical bytes Q_D;
dftracer-utils supplies only the matching layer's event count and cumulative
duration. This keeps memory, MPI-IO, and POSIX-I/O points on the common axes
W/Q_D and W/T without equating their native operations. Communication is
intentionally deferred.
"""

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_TRACE = Path(
    "/home/cc/traces/26/08/23/"
    "trace-cc-mpi-io-full-2rank-xio-rooflines-ior-full-syscalls.pfw.gz"
)
DEFAULT_VENV_SITE_PACKAGES = Path(
    "/home/cc/dftracer-utils-develop/.dftracer_venv/lib/python3.10/site-packages"
)

MPIIO_DATA_FUNCTIONS = [
    "MPI_File_read",
    "MPI_File_read_at",
    "MPI_File_read_all",
    "MPI_File_read_at_all",
    "MPI_File_write",
    "MPI_File_write_at",
    "MPI_File_write_all",
    "MPI_File_write_at_all",
    "MPI_File_iread",
    "MPI_File_iread_at",
    "MPI_File_iwrite",
    "MPI_File_iwrite_at",
]
MPIIO_FUNCTIONS = ["MPI_File_open", "MPI_File_close", *MPIIO_DATA_FUNCTIONS]
POSIX_IO_NAMES = ["openat", "read", "write", "close", "fsync"]
MEMORY_SYSCALLS = ["mmap", "munmap", "brk", "mprotect"]
LAYERS = {
    "memory": MEMORY_SYSCALLS,
    "mpi_io": MPIIO_FUNCTIONS,
    "posix_io": POSIX_IO_NAMES,
}


def import_dftracer(venv_site_packages):
    try:
        from dftracer.utils import Field, TraceViewer

        return TraceViewer, Field
    except ImportError:
        pass
    if venv_site_packages.is_dir():
        sys.path.insert(0, str(venv_site_packages))
        try:
            from dftracer.utils import Field, TraceViewer

            return TraceViewer, Field
        except ImportError:
            pass
    raise SystemExit(
        "dftracer-utils is not importable; use its venv Python or pass "
        "--dftracer-venv-site-packages."
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, nargs="+", default=[DEFAULT_TRACE])
    parser.add_argument("--logical-bytes", type=float, required=True, help="Logical application bytes Q_D.")
    parser.add_argument(
        "--logical-dataops",
        type=int,
        help="Logical DataOp count W; otherwise count --dataop-events in the trace.",
    )
    parser.add_argument(
        "--dataop-events",
        nargs="+",
        default=MPIIO_DATA_FUNCTIONS,
        help="Events defining one logical DataOp when --logical-dataops is omitted.",
    )
    parser.add_argument(
        "--dataop-definition",
        default="one traced MPI-IO data-transfer call",
        help="Auditable description written into every point row.",
    )
    for layer in LAYERS:
        parser.add_argument(
            f"--{layer.replace('_', '-')}-seconds",
            type=float,
            help=f"Override cumulative traced {layer} duration.",
        )
    parser.add_argument(
        "--dftracer-venv-site-packages",
        type=Path,
        default=DEFAULT_VENV_SITE_PACKAGES,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA / "dataop_memory_io_points_dftracer.csv",
    )
    return parser.parse_args()


def query_count_seconds(view, Field, names):
    result = view.filter(Field("name").is_in(names)).agg("count", "sum:dur").collect().to_pandas()
    if result.empty or int(result["count"].iloc[0]) == 0:
        return 0, 0.0
    return int(result["count"].iloc[0]), float(result["sum_dur"].iloc[0]) / 1.0e6


def main():
    args = parse_arguments()
    if args.logical_bytes <= 0.0:
        raise SystemExit("--logical-bytes must be greater than zero")
    if args.logical_dataops is not None and args.logical_dataops <= 0:
        raise SystemExit("--logical-dataops must be greater than zero")
    for trace in args.trace:
        if not trace.exists():
            raise SystemExit(f"trace not found: {trace}")

    TraceViewer, Field = import_dftracer(args.dftracer_venv_site_packages)
    view = TraceViewer([str(path) for path in args.trace]).time_unit("us")
    source_count, _ = query_count_seconds(view, Field, args.dataop_events)
    logical_dataops = args.logical_dataops if args.logical_dataops is not None else source_count
    if logical_dataops <= 0:
        raise SystemExit("no logical DataOps observed; pass --logical-dataops or correct --dataop-events")

    rows = []
    for layer, names in LAYERS.items():
        native_count, traced_seconds = query_count_seconds(view, Field, names)
        override_seconds = getattr(args, f"{layer}_seconds")
        duration_seconds = override_seconds if override_seconds is not None else traced_seconds
        if native_count == 0 or duration_seconds <= 0.0:
            print(f"skipping {layer}: no matching events or positive duration")
            continue
        rows.append(
            {
                "point": layer,
                "data_intensity_dataops_per_byte": f"{logical_dataops / args.logical_bytes:.12g}",
                "dataop_rate_per_second": f"{logical_dataops / duration_seconds:.12g}",
                "logical_dataops": logical_dataops,
                "logical_bytes": f"{args.logical_bytes:.12g}",
                "native_event_count": native_count,
                "duration_seconds": f"{duration_seconds:.12g}",
                "duration_semantics": "override" if override_seconds is not None else "cumulative traced event duration",
                "dataop_definition": args.dataop_definition,
                "event_names": ";".join(names),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "point",
        "data_intensity_dataops_per_byte",
        "dataop_rate_per_second",
        "logical_dataops",
        "logical_bytes",
        "native_event_count",
        "duration_seconds",
        "duration_semantics",
        "dataop_definition",
        "event_names",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"logical_dataops={logical_dataops} logical_bytes={args.logical_bytes}")
    print(f"points={args.output} points_count={len(rows)}")
    if len(rows) != len(LAYERS):
        print("fewer than three points emitted; absent layers were not fabricated")


if __name__ == "__main__":
    main()