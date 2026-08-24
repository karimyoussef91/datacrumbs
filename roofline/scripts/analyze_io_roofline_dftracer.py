#!/usr/bin/env python3
"""Derive I/O roofline points from DataCrumbs traces using dftracer-utils.

Parses one or more .pfw.gz traces with dftracer.utils.TraceViewer instead of
manual gzip/json parsing (see analyze_io_roofline.py, kept unchanged). Follows
the same model as analyze_io_roofline.py: Zhu & Neuwirth (ICPADS'23),
IOI = theta / sigma, Attainable Performance (IOPS) = min(psi, kappa * IOI).

Requires the dftracer-utils Python package. If it is not importable from the
current interpreter, this script falls back to the venv built alongside
/home/cc/dftracer-utils-develop (override with --dftracer-venv-site-packages),
otherwise run it directly with that venv's python.
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
DEFAULT_WORKLOAD_BYTES = 33554432
DEFAULT_APPLICATION_SECONDS = 0.048344
POSIX_IO_NAMES = ["openat", "read", "write", "close", "fsync"]
MPIIO_FUNCTIONS = [
    "MPI_File_open",
    "MPI_File_close",
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
MPI_COMM_FUNCTIONS = [
    "MPI_Send",
    "MPI_Recv",
    "MPI_Isend",
    "MPI_Irecv",
    "MPI_Wait",
    "MPI_Waitall",
    "MPI_Bcast",
    "MPI_Barrier",
    "MPI_Allreduce",
]
MEMORY_SYSCALLS = ["mmap", "munmap", "brk", "mprotect"]


def import_trace_viewer(venv_site_packages: Path):
    try:
        from dftracer.utils import TraceViewer

        return TraceViewer
    except ImportError:
        pass
    if venv_site_packages.is_dir():
        sys.path.insert(0, str(venv_site_packages))
        try:
            from dftracer.utils import TraceViewer

            return TraceViewer
        except ImportError:
            pass
    raise SystemExit(
        "dftracer-utils is not importable. Either run this script with "
        f"{DEFAULT_VENV_SITE_PACKAGES.parent.parent}/bin/python3, or pass "
        "--dftracer-venv-site-packages pointing at its site-packages directory."
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace",
        type=Path,
        nargs="+",
        default=[DEFAULT_TRACE],
        help="One or more .pfw.gz trace files (or a directory) to parse.",
    )
    parser.add_argument(
        "--dftracer-venv-site-packages",
        type=Path,
        default=DEFAULT_VENV_SITE_PACKAGES,
        help="Fallback site-packages directory if dftracer-utils is not on sys.path.",
    )
    parser.add_argument(
        "--workload-bytes",
        type=float,
        default=DEFAULT_WORKLOAD_BYTES,
        help="Total bytes moved (sigma) for the traced workload.",
    )
    parser.add_argument(
        "--application-seconds",
        type=float,
        default=DEFAULT_APPLICATION_SECONDS,
        help="End-to-end application wall time (write+read phases).",
    )
    parser.add_argument("--posix-seconds", type=float, help="Override the cumulative POSIX duration.")
    parser.add_argument("--mpiio-seconds", type=float, help="Override the cumulative MPI-IO duration.")
    parser.add_argument("--mpi-comm-seconds", type=float, help="Override the cumulative MPI communication duration.")
    parser.add_argument("--memory-seconds", type=float, help="Override the cumulative memory syscall duration.")
    parser.add_argument(
        "--system-csv",
        type=Path,
        default=DATA / "io_roofline_system.csv",
        help="CSV from run_io_roofline_benchmark.sh with peak_iops and peak_bandwidth.",
    )
    parser.add_argument(
        "--points-output",
        type=Path,
        default=DATA / "io_roofline_points_dftracer.csv",
        help="Output CSV path for the derived IOPS/IOI points.",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        default=ROOT / "io_roofline_dftracer_four_points.png",
        help="Output PNG path for the roofline plot.",
    )
    return parser.parse_args()


def query_theta_seconds(view, names):
    """Return (theta, cumulative_seconds) for events whose name is in `names`."""
    quoted = "[" + ", ".join(f'"{name}"' for name in names) + "]"
    table = view.filter(f"name in {quoted}").agg("count", "sum:dur").collect()
    df = table.to_pandas()
    if df.empty or df["count"].iloc[0] == 0:
        return 0, 0.0
    return int(df["count"].iloc[0]), float(df["sum_dur"].iloc[0]) / 1.0e6


def read_system_metrics(path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = {row["metric"]: row for row in csv.DictReader(stream)}
    return float(rows["peak_iops"]["value"]), float(rows["peak_bandwidth"]["value"])


def plot_roofline(system_csv, rows, output_path):
    import numpy as np
    import matplotlib.pyplot as plt

    peak_iops, peak_bandwidth_gbs = read_system_metrics(system_csv)
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

    colors = {
        "overall_application": "#6f2dbd",
        "mpi_io": "#1f7a1f",
        "posix": "#9b2226",
        "mpi_comm": "#0a6ebd",
        "memory": "#c9781f",
    }
    for row in rows:
        if row["ioi"] > 0.0 and row["iops"] > 0.0:
            axis.scatter(
                [row["ioi"]],
                [row["iops"]],
                s=90,
                marker="o",
                color=colors.get(row["layer"], "#333333"),
                edgecolor="white",
                linewidth=1.1,
                zorder=6,
                label=f"Trace point (dftracer-utils): {row['layer'].replace('_', ' ')}",
            )

    axis.set_title("I/O Roofline Model (parsed with dftracer-utils)")
    axis.set_xlabel("I/O operational intensity [IOP/byte]")
    axis.set_ylabel("Attainable performance [IOPS]")
    axis.set_xlim(ioi[0], ioi[-1])
    axis.set_ylim(1e-1, peak_iops * 3)
    axis.grid(True, which="both", color="#d6d6d6", linewidth=0.6)
    axis.legend(loc="lower right", frameon=True, fontsize=9)
    fig.savefig(output_path, dpi=180)


def main():
    args = parse_arguments()
    TraceViewer = import_trace_viewer(args.dftracer_venv_site_packages)

    trace_paths = [str(path) for path in args.trace]
    for path in args.trace:
        if not path.exists():
            raise SystemExit(f"trace not found: {path}")
    DATA.mkdir(exist_ok=True)

    view = TraceViewer(trace_paths).time_unit("us")
    theta_posix, seconds_posix = query_theta_seconds(view, POSIX_IO_NAMES)
    theta_mpiio, seconds_mpiio = query_theta_seconds(view, MPIIO_FUNCTIONS)
    theta_mpi_comm, seconds_mpi_comm = query_theta_seconds(view, MPI_COMM_FUNCTIONS)
    theta_memory, seconds_memory = query_theta_seconds(view, MEMORY_SYSCALLS)
    posix_seconds = args.posix_seconds if args.posix_seconds is not None else seconds_posix
    mpiio_seconds = args.mpiio_seconds if args.mpiio_seconds is not None else seconds_mpiio
    mpi_comm_seconds = args.mpi_comm_seconds if args.mpi_comm_seconds is not None else seconds_mpi_comm
    memory_seconds = args.memory_seconds if args.memory_seconds is not None else seconds_memory

    workload_bytes = args.workload_bytes

    rows = []
    if workload_bytes > 0.0:
        if theta_mpiio > 0 and mpiio_seconds > 0.0:
            rows.append(
                {
                    "layer": "mpi_io",
                    "ioi": theta_mpiio / workload_bytes,
                    "iops": theta_mpiio / mpiio_seconds,
                    "theta": theta_mpiio,
                    "sigma_bytes": workload_bytes,
                    "duration_seconds": mpiio_seconds,
                    "semantics": "Cumulative traced MPI_File_* duration via dftracer-utils; overhead-inclusive.",
                }
            )
        if theta_posix > 0 and posix_seconds > 0.0:
            rows.append(
                {
                    "layer": "posix",
                    "ioi": theta_posix / workload_bytes,
                    "iops": theta_posix / posix_seconds,
                    "theta": theta_posix,
                    "sigma_bytes": workload_bytes,
                    "duration_seconds": posix_seconds,
                    "semantics": "Cumulative traced POSIX syscall duration via dftracer-utils; overhead-inclusive.",
                }
            )
        if theta_mpi_comm > 0 and mpi_comm_seconds > 0.0:
            rows.append(
                {
                    "layer": "mpi_comm",
                    "ioi": theta_mpi_comm / workload_bytes,
                    "iops": theta_mpi_comm / mpi_comm_seconds,
                    "theta": theta_mpi_comm,
                    "sigma_bytes": workload_bytes,
                    "duration_seconds": mpi_comm_seconds,
                    "semantics": "Cumulative traced MPI comm duration via dftracer-utils; not I/O work, plotted for scale.",
                }
            )
        if theta_memory > 0 and memory_seconds > 0.0:
            rows.append(
                {
                    "layer": "memory",
                    "ioi": theta_memory / workload_bytes,
                    "iops": theta_memory / memory_seconds,
                    "theta": theta_memory,
                    "sigma_bytes": workload_bytes,
                    "duration_seconds": memory_seconds,
                    "semantics": "Cumulative traced mmap/munmap/brk/mprotect duration via dftracer-utils; not I/O work, plotted for scale.",
                }
            )

    with args.points_output.open("w", newline="", encoding="utf-8") as stream:
        fields = ["layer", "ioi", "iops", "theta", "sigma_bytes", "duration_seconds", "semantics"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "ioi": f"{row['ioi']:.12g}",
                    "iops": f"{row['iops']:.12g}",
                    "sigma_bytes": f"{row['sigma_bytes']:.12g}",
                    "duration_seconds": f"{row['duration_seconds']:.12g}",
                }
            )

    print(f"trace={trace_paths}")
    print(f"theta_posix={theta_posix} theta_mpiio={theta_mpiio} theta_mpi_comm={theta_mpi_comm} theta_memory={theta_memory}")
    print(f"cumulative_posix_seconds={seconds_posix:.6f} cumulative_mpiio_seconds={seconds_mpiio:.6f} "
          f"cumulative_mpi_comm_seconds={seconds_mpi_comm:.6f} cumulative_memory_seconds={seconds_memory:.6f}")
    print(f"points={args.points_output}")
    print(f"points_count={len(rows)}")
    if theta_mpiio == 0:
        print("mpi_io layer not observed: this trace has no MPI_File_* events.")

    if args.system_csv.is_file() and rows:
        plot_roofline(args.system_csv, rows, args.plot_output)
        print(f"plot={args.plot_output}")
    elif not args.system_csv.is_file():
        print(f"skipping plot: system CSV not found at {args.system_csv}")


if __name__ == "__main__":
    main()
