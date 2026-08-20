#!/usr/bin/env python3
"""Development-only signed probe generator for combined POSIX + MPI-IO tracing.

Adds an HMAC-signed probe document with two categories: the same core-only
POSIX syscall set used elsewhere, plus a UPROBE category attached to the
MPI-IO entry points in the linked libmpi.so, so a single trace captures both
I/O stack layers for roofline analysis. Do not use this outside local testing.
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
