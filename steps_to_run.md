# Steps to Run DataCrumbs

This is the exact workflow used on this node (`xio-rooflines`) to generate
signed probes, run the DataCrumbs runtime, trace an IOR workload, and locate
the resulting trace file. DataCrumbs core is installed at
`$HOME/.local/datacrumbs` and configured to write traces under
`$HOME/traces`.

## 1. Generate Probes

Probes define which functions DataCrumbs instruments. Every probe file is
HMAC-signed with the root-owned secret at
`$HOME/.local/datacrumbs/share/datacrumbs/data/.datacrumbs-probe-secret`
(mode `0600`, owned by `root`).

**Production path** (requires the separate `datacrumbs-utils` package, not
installed on this node):

```bash
datacrumbs_probe_configurator \
  <install-prefix>/etc/datacrumbs/configs/<host>.yaml \
  /tmp/probes.json.gz
```

**What we actually used here** (core-only, development-only probe
generators in `scripts/testing/`, since `datacrumbs-utils` is not installed):

POSIX syscalls only:

```bash
sudo python3 scripts/testing/generate_core_only_probe.py \
  "$HOME/.local/datacrumbs/share/datacrumbs/data/.datacrumbs-probe-secret" \
  "$HOME/traces/probes/ior-mpi-syscalls.json"
```

POSIX syscalls **and** MPI-IO calls (uprobes on `libmpi.so`), for a
POSIX + MPI-IO layered trace:

```bash
libmpi_real=$(readlink -f /lib/x86_64-linux-gnu/libmpi.so.40)
sudo python3 scripts/testing/generate_core_only_mpiio_probe.py \
  "$HOME/.local/datacrumbs/share/datacrumbs/data/.datacrumbs-probe-secret" \
  "$libmpi_real" \
  "$HOME/traces/probes/ior-mpiio-syscalls.json"
```

Both scripts require `sudo` because only `root` can read the signing secret.

## 2. Start the DataCrumbs Runtime

Start the runtime as `root`, passing the signed probe file and a run ID:

```bash
sudo /home/cc/.local/datacrumbs/sbin/datacrumbs \
  /home/cc/traces/probes/ior-mpiio-syscalls.json \
  mpi-io-2rank-v2 \
  cc
```

Wait for the log line:

```text
[INFO] DataCrumbs ready to run for user:cc run_id:mpi-io-2rank-v2 trace_file:...
```

That line also reports the exact trace file path this run will produce.

## 3. Run the Traced Workload

Since `datacrumbs-utils` (and `datacrumbs_wrap`) is not installed here, use
the development-only client shim so the traced process registers with the
runtime:

```bash
export LD_PRELOAD="$HOME/traces/core_only_client_shim.so${LD_PRELOAD:+:$LD_PRELOAD}"
mpirun -np 2 -x LD_PRELOAD "$HOME/.local/ior/bin/ior" \
  -a MPIIO -b 4m -t 1m -s 2 -F -w -r -e \
  -o "$HOME/traces/work/ior-mpiio-2rank-v2"
```

In production, this step is instead:

```bash
datacrumbs_wrap ./myapp arg1 arg2
```

## 4. Stop the Runtime

Send `SIGINT` to the running `datacrumbs` process to flush and finalize the
trace:

```bash
sudo kill -INT "$(pgrep -xo datacrumbs)"
```

Wait for:

```text
[PRINT] Collected <N> events and failed 0 events
```

## 5. Locate and Inspect the Trace

Traces are written under the configured trace directory, following the
pattern `<trace-dir>/%YY%/%MM%/%DD%/trace-<user>-<run-id>-<host>-<probe-stem>.pfw.gz`:

```text
/home/cc/traces/26/08/20/trace-cc-mpi-io-2rank-v2-xio-rooflines-ior-mpiio-syscalls.pfw.gz
```

Inspect it:

```bash
gzip -cd /home/cc/traces/26/08/20/trace-cc-mpi-io-2rank-v2-xio-rooflines-ior-mpiio-syscalls.pfw.gz | jq .
```

## Probe File Reference

| Probe file | Categories | Used for |
| --- | --- | --- |
| `$HOME/traces/probes/ior-mpi-syscalls.json` | POSIX syscalls only (`read`, `write`, `openat`, `close`, `fsync`) | POSIX-only IOR trace |
| `$HOME/traces/probes/ior-mpiio-syscalls.json` | POSIX syscalls + MPI-IO uprobes (`MPI_File_open`, `MPI_File_read_at`, `MPI_File_write_at`, `MPI_File_close`, etc.) on `libmpi.so.40` | Combined POSIX + MPI-IO layered trace |

## Notes for the Meeting

- Direct `datacrumbs` invocation is root-only because the signing secret is
  reused for runtime probe verification.
- Normal multi-user deployments should use `datacrumbs@<run-id>.service`
  (systemd) instead of the direct CLI shown here; see
  `.github/skills/datacrumbs-build-install/SKILL.md` for that path.
- The core-only probe generators and client shim used above are
  development/testing helpers only, needed here because `datacrumbs-utils`
  is not installed on this node.
