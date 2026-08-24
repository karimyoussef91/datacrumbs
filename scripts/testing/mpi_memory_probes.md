# MPI Communication and Memory Probe Categories

This documents how MPI point-to-point/collective communication and
memory-management calls were added to the DataCrumbs probe used for IOR
tracing, and the steps to reproduce a trace containing all four layers.

## What Was Added

[scripts/testing/generate_core_only_mpiio_probe.py](../scripts/testing/generate_core_only_mpiio_probe.py)
now generates four categories instead of two:

| Category name | `type` | Mechanism | Functions |
| --- | --- | --- | --- |
| `ior-posix-syscalls` | `0` (`SYSCALLS`) | kernel syscall tracepoints | `read`, `write`, `openat`, `close`, `fsync` |
| `ior-mpiio-uprobes` | `2` (`UPROBE`) | uprobes on `libmpi.so` | `MPI_File_open/close/read/read_at/read_all/read_at_all/write/write_at/write_all/write_at_all/iread/iread_at/iwrite/iwrite_at` |
| `ior-mpi-comm-uprobes` | `2` (`UPROBE`) | uprobes on `libmpi.so` | `MPI_Send`, `MPI_Recv`, `MPI_Isend`, `MPI_Irecv`, `MPI_Wait`, `MPI_Waitall`, `MPI_Bcast`, `MPI_Barrier`, `MPI_Allreduce` |
| `ior-memory-syscalls` | `0` (`SYSCALLS`) | kernel syscall tracepoints | `mmap`, `munmap`, `brk`, `mprotect` |

The MPI communication functions reuse the same `binary_path` (the resolved
`libmpi.so`) already used for MPI-IO; the memory syscalls are plain
`SYSCALLS`-type entries, identical in mechanism to the existing POSIX category.

## Steps to Reproduce

1. **Confirm the target symbols exist** (only needed once per environment):

   ```bash
   libmpi_real=$(readlink -f /lib/x86_64-linux-gnu/libmpi.so.40)
   nm -D "$libmpi_real" | grep -E ' T MPI_(Send|Recv|Isend|Irecv|Wait|Waitall|Bcast|Barrier|Allreduce)$'
   grep -E '__x64_sys_(mmap|munmap|brk|mprotect)$' /proc/kallsyms
   ```

2. **Generate and sign the four-category probe**:

   ```bash
   libmpi_real=$(readlink -f /lib/x86_64-linux-gnu/libmpi.so.40)
   sudo python3 scripts/testing/generate_core_only_mpiio_probe.py \
     "$HOME/.local/datacrumbs/share/datacrumbs/data/.datacrumbs-probe-secret" \
     "$libmpi_real" \
     "$HOME/traces/probes/ior-full-syscalls.json"
   ```

3. **Start the DataCrumbs runtime** with the new probe:

   ```bash
   sudo /home/cc/.local/datacrumbs/sbin/datacrumbs \
     /home/cc/traces/probes/ior-full-syscalls.json \
     mpi-io-full-2rank \
     cc
   ```

   Wait for `Runtime probe attachment summary: requested=64 attached=64 failed=0`
   (32 functions x entry/exit).

4. **Run the traced workload** (same IOR MPI-IO command as before):

   ```bash
   export LD_PRELOAD="$HOME/traces/core_only_client_shim.so${LD_PRELOAD:+:$LD_PRELOAD}"
   mpirun -np 2 -x LD_PRELOAD "$HOME/.local/ior/bin/ior" \
     -a MPIIO -b 4m -t 1m -s 2 -F -w -r -e \
     -o "$HOME/traces/work/ior-full-2rank"
   ```

5. **Stop the runtime**:

   ```bash
   sudo kill -INT "$(pgrep -xo datacrumbs)"
   ```

6. **Verify all four categories are present** (using dftracer-utils):

   ```bash
   /home/cc/dftracer-utils-develop/.dftracer_venv/bin/python3 - <<'PY'
   from dftracer.utils import TraceViewer

   trace = "/home/cc/traces/26/08/23/trace-cc-mpi-io-full-2rank-xio-rooflines-ior-full-syscalls.pfw.gz"
   view = TraceViewer([trace]).time_unit("us")
   df = view.group_by("cat", "name").agg("count", "sum:dur").collect().to_pandas()
   print(df.sort_values(["cat", "name"]).to_string(index=False))
   PY
   ```

## Result

The resulting trace
(`/home/cc/traces/26/08/23/trace-cc-mpi-io-full-2rank-xio-rooflines-ior-full-syscalls.pfw.gz`,
11,993 events) contains all four categories:

```text
ior-memory-syscalls    brk               61
ior-memory-syscalls    mmap            1379
ior-memory-syscalls    mprotect         382
ior-memory-syscalls    munmap           360
ior-mpi-comm-uprobes   MPI_Allreduce     12
ior-mpi-comm-uprobes   MPI_Barrier       12
ior-mpi-comm-uprobes   MPI_Bcast          8
ior-mpiio-uprobes      MPI_File_close    10
ior-mpiio-uprobes      MPI_File_open     12
ior-mpiio-uprobes      MPI_File_read_at  16
ior-mpiio-uprobes      MPI_File_write_at 16
ior-posix-syscalls     close            937
ior-posix-syscalls     fsync              2
ior-posix-syscalls     openat          4386
ior-posix-syscalls     read            4210
ior-posix-syscalls     write            190
```

`MPI_Send`/`MPI_Recv`/`MPI_Isend`/`MPI_Irecv`/`MPI_Wait`/`MPI_Waitall` were
probed but not hit (`0` count) because this IOR run used independent,
file-per-process MPI-IO with no explicit point-to-point message passing; only
the collective calls IOR's MPI-IO backend issues internally
(`MPI_Bcast`/`MPI_Barrier`/`MPI_Allreduce`) fired.
