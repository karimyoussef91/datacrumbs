#!/usr/bin/env python3
"""Development-only signed probe generator for POSIX + MPI-IO + MPI comm + memory tracing.

Adds an HMAC-signed probe document with four categories: the core-only POSIX
syscall set, MPI-IO uprobes, MPI point-to-point/collective communication
uprobes, and memory-management syscalls, all attached to the linked libmpi.so
and the kernel respectively, so a single trace covers all four layers for
roofline/analysis work. Do not use this outside local testing.
"""
import hashlib
import hmac
import json
import sys
from pathlib import Path


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


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"usage: {sys.argv[0]} <secret-file> <libmpi-path> <output-probes.json>",
            file=sys.stderr,
        )
        return 2

    secret = Path(sys.argv[1]).read_text(encoding="ascii")
    libmpi_path = sys.argv[2]
    categories = [
        {
            "type": 0,
            "name": "ior-posix-syscalls",
            "functions": ["read", "write", "openat", "close", "fsync"],
        },
        {
            "type": 2,
            "name": "ior-mpiio-uprobes",
            "binary_path": libmpi_path,
            "include_offsets": False,
            "functions": MPIIO_FUNCTIONS,
        },
        {
            "type": 2,
            "name": "ior-mpi-comm-uprobes",
            "binary_path": libmpi_path,
            "include_offsets": False,
            "functions": MPI_COMM_FUNCTIONS,
        },
        {
            "type": 0,
            "name": "ior-memory-syscalls",
            "functions": MEMORY_SYSCALLS,
        },
    ]
    summary = {"source": "core-only-local-ior-mpiio-test"}
    payload = json.dumps(
        {
            "summary": summary,
            "categories": categories,
            "checksum_algorithm": "hmac-sha256",
        },
        separators=(",", ":"),
    )
    # json-c's JSON_C_TO_STRING_PLAIN still escapes '/' as '\/'; json.dumps does not.
    payload = payload.replace("/", "\\/")
    document = {
        "summary": summary,
        "categories": categories,
        "checksum_algorithm": "hmac-sha256",
        "checksum": hmac.new(secret.encode("ascii"), payload.encode("utf-8"), hashlib.sha256).hexdigest(),
    }
    Path(sys.argv[3]).write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
