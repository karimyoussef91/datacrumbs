#!/usr/bin/env python3
"""Derive I/O roofline points (IOPS vs. IOI) from a DataCrumbs IOR trace.

Follows Zhu & Neuwirth (ICPADS'23): I/O intensity lambda = theta / sigma, where
theta is the count of traced I/O operations for a given interface (POSIX set
alpha or MPI-IO set beta) and sigma is the total bytes moved. Attainable
performance for a point is theta / elapsed_seconds for that interface.

Traces without byte arguments or MPI-IO events require sigma and elapsed times
to be supplied as recorded IOR metadata or via CLI overrides; this script never
fabricates missing values, and only emits a layer's point when its theta > 0.
"""

import argparse
import csv
import gzip
import json
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
POSIX_IO_NAMES = {"openat", "read", "write", "close", "fsync"}
MPIIO_NAME_PREFIX = "MPI_File_"
MPI_COMM_NAMES = {
    "MPI_Send",
    "MPI_Recv",
    "MPI_Isend",
    "MPI_Irecv",
    "MPI_Wait",
    "MPI_Waitall",
    "MPI_Bcast",
    "MPI_Barrier",
    "MPI_Allreduce",
}
MEMORY_SYSCALL_NAMES = {"mmap", "munmap", "brk", "mprotect"}


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help="DataCrumbs .pfw.gz trace")
    parser.add_argument(
        "--workload-bytes",
        type=float,
        help="Total bytes moved (sigma); defaults to the known 32 MiB two-rank phase.",
    )
    parser.add_argument(
        "--application-seconds",
        type=float,
        help="End-to-end application wall time; defaults to the recorded write+read phase time.",
    )
    parser.add_argument(
        "--posix-seconds",
        type=float,
        help="POSIX layer wall time; default is the sum of observed POSIX syscall durations.",
    )
    parser.add_argument(
        "--mpiio-seconds",
        type=float,
        help="MPI-IO layer wall time; default is the sum of observed MPI_File_* durations.",
    )
    parser.add_argument(
        "--mpi-comm-seconds",
        type=float,
        help="MPI communication layer wall time; default is the sum of observed durations.",
    )
    parser.add_argument(
        "--memory-seconds",
        type=float,
        help="Memory syscall layer wall time; default is the sum of observed durations.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA / "io_roofline_points.csv",
        help="Output CSV path for the derived IOPS/IOI points.",
    )
    return parser.parse_args()


def load_trace(trace_path):
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        events = json.load(stream)
    if not isinstance(events, list):
        raise ValueError("expected a Chrome/Perfetto JSON event array")
    return events


def layer_theta(events, is_layer_name):
    """Return (theta, cumulative_seconds) for the events matching is_layer_name."""
    relevant = [event for event in events if event.get("ph") == "X" and is_layer_name(event.get("name", ""))]
    theta = len(relevant)
    cumulative_seconds = sum(float(event.get("dur", 0.0)) for event in relevant) / 1.0e6
    return theta, cumulative_seconds


def trace_theta(events):
    """Return per-interface theta/seconds per the paper's POSIX (alpha) and MPI-IO (beta) sets,
    plus the MPI communication and memory syscall layers."""
    theta_posix, seconds_posix = layer_theta(events, lambda name: name in POSIX_IO_NAMES)
    theta_mpiio, seconds_mpiio = layer_theta(events, lambda name: name.startswith(MPIIO_NAME_PREFIX))
    theta_mpi_comm, seconds_mpi_comm = layer_theta(events, lambda name: name in MPI_COMM_NAMES)
    theta_memory, seconds_memory = layer_theta(events, lambda name: name in MEMORY_SYSCALL_NAMES)
    return (
        theta_posix,
        seconds_posix,
        theta_mpiio,
        seconds_mpiio,
        theta_mpi_comm,
        seconds_mpi_comm,
        theta_memory,
        seconds_memory,
    )


def default_ior_metadata(trace_path):
    """Return recorded phase metadata only for the known local two-rank POSIX trace."""
    if trace_path.resolve() != DEFAULT_TRACE.resolve():
        return None
    return {
        "bytes": DEFAULT_IOR_PHASE_BYTES * 2,
        "application_seconds": DEFAULT_IOR_WRITE_SECONDS + DEFAULT_IOR_READ_SECONDS,
    }


def main():
    args = parse_arguments()
    if not args.trace.is_file():
        raise SystemExit(f"trace not found: {args.trace}")
    DATA.mkdir(exist_ok=True)

    (
        theta_posix,
        seconds_posix,
        theta_mpiio,
        seconds_mpiio,
        theta_mpi_comm,
        seconds_mpi_comm,
        theta_memory,
        seconds_memory,
    ) = trace_theta(load_trace(args.trace))
    posix_seconds = args.posix_seconds if args.posix_seconds is not None else seconds_posix
    mpiio_seconds = args.mpiio_seconds if args.mpiio_seconds is not None else seconds_mpiio
    mpi_comm_seconds = args.mpi_comm_seconds if args.mpi_comm_seconds is not None else seconds_mpi_comm
    memory_seconds = args.memory_seconds if args.memory_seconds is not None else seconds_memory

    defaults = default_ior_metadata(args.trace) or {}
    workload_bytes = args.workload_bytes if args.workload_bytes is not None else defaults.get("bytes")
    application_seconds = (
        args.application_seconds if args.application_seconds is not None else defaults.get("application_seconds")
    )

    rows = []
    if workload_bytes is not None and workload_bytes > 0.0:
        if theta_mpiio > 0 and mpiio_seconds > 0.0:
            rows.append(
                {
                    "layer": "mpi_io",
                    "ioi": f"{theta_mpiio / workload_bytes:.12g}",
                    "iops": f"{theta_mpiio / mpiio_seconds:.12g}",
                    "theta": theta_mpiio,
                    "sigma_bytes": f"{workload_bytes:.12g}",
                    "duration_seconds": f"{mpiio_seconds:.12g}",
                    "semantics": "Cumulative traced MPI_File_* duration; overhead-inclusive.",
                }
            )
        if theta_posix > 0 and posix_seconds > 0.0:
            rows.append(
                {
                    "layer": "posix",
                    "ioi": f"{theta_posix / workload_bytes:.12g}",
                    "iops": f"{theta_posix / posix_seconds:.12g}",
                    "theta": theta_posix,
                    "sigma_bytes": f"{workload_bytes:.12g}",
                    "duration_seconds": f"{posix_seconds:.12g}",
                    "semantics": "Cumulative traced POSIX syscall duration; overhead-inclusive.",
                }
            )
        if theta_mpi_comm > 0 and mpi_comm_seconds > 0.0:
            rows.append(
                {
                    "layer": "mpi_comm",
                    "ioi": f"{theta_mpi_comm / workload_bytes:.12g}",
                    "iops": f"{theta_mpi_comm / mpi_comm_seconds:.12g}",
                    "theta": theta_mpi_comm,
                    "sigma_bytes": f"{workload_bytes:.12g}",
                    "duration_seconds": f"{mpi_comm_seconds:.12g}",
                    "semantics": "Cumulative traced MPI point-to-point/collective duration; not I/O work, plotted against the same workload bytes for scale.",
                }
            )
        if theta_memory > 0 and memory_seconds > 0.0:
            rows.append(
                {
                    "layer": "memory",
                    "ioi": f"{theta_memory / workload_bytes:.12g}",
                    "iops": f"{theta_memory / memory_seconds:.12g}",
                    "theta": theta_memory,
                    "sigma_bytes": f"{workload_bytes:.12g}",
                    "duration_seconds": f"{memory_seconds:.12g}",
                    "semantics": "Cumulative traced mmap/munmap/brk/mprotect duration; not I/O work, plotted against the same workload bytes for scale.",
                }
            )

    with args.output.open("w", newline="", encoding="utf-8") as stream:
        fields = ["layer", "ioi", "iops", "theta", "sigma_bytes", "duration_seconds", "semantics"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"trace={args.trace}")
    print(f"theta_posix={theta_posix} theta_mpiio={theta_mpiio} theta_mpi_comm={theta_mpi_comm} theta_memory={theta_memory}")
    print(f"cumulative_posix_seconds={seconds_posix:.6f} cumulative_mpiio_seconds={seconds_mpiio:.6f} "
          f"cumulative_mpi_comm_seconds={seconds_mpi_comm:.6f} cumulative_memory_seconds={seconds_memory:.6f}")
    print(f"points={args.output}")
    print(f"points_count={len(rows)}")
    if theta_mpiio == 0:
        print("mpi_io layer not observed: this trace has no MPI_File_* events.")
    if not rows:
        print("No I/O roofline points emitted: supply --workload-bytes and --application-seconds.")


if __name__ == "__main__":
    main()
