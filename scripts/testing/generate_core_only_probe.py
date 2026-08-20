#!/usr/bin/env python3
import hashlib
import hmac
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <secret-file> <output-probes.json>", file=sys.stderr)
        return 2

    secret = Path(sys.argv[1]).read_text(encoding="ascii")
    categories = [
        {
            "type": 0,
            "name": "ior-posix-syscalls",
            "functions": ["read", "write", "openat", "close", "fsync"],
        }
    ]
    summary = {"source": "core-only-local-ior-test"}
    payload = json.dumps(
        {
            "summary": summary,
            "categories": categories,
            "checksum_algorithm": "hmac-sha256",
        },
        separators=(",", ":"),
    )
    document = {
        "summary": summary,
        "categories": categories,
        "checksum_algorithm": "hmac-sha256",
        "checksum": hmac.new(secret.encode("ascii"), payload.encode("utf-8"), hashlib.sha256).hexdigest(),
    }
    Path(sys.argv[2]).write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())