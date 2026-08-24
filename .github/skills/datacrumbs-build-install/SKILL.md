---
name: datacrumbs-build-install
description: "Build, install, and deploy DataCrumbs on Linux. Use when configuring CMake, resolving build prerequisites, installing into a shared prefix, setting up eBPF tracing, systemd services, Flux or SLURM integration, permissions, resource limits, or runtime validation."
argument-hint: "[install-prefix] [scheduler: FLUX|SLURM|OPENMPI|NONE]"
---

# Build and Install DataCrumbs

Use this workflow to build DataCrumbs from this repository and deploy it safely
on Linux systems. Default to the local developer install below; treat production
HPC deployment as a separate outcome. Compiling does not require root, while the
supported eBPF runtime and trusted signing services do.

## Inputs

Determine these values before configuring:

- Installation prefix, shared by `datacrumbs` and `datacrumbs-utils`.
- Target host name and the runtime user.
- Install user, which owns per-user runtime-status SQLite databases.
- Scheduler: `FLUX`, `SLURM`, `OPENMPI`, or `NONE`.
- Trace, log, and runtime-state directories. Use durable, writable locations in
  production instead of the `/tmp` defaults.

## 1. Preflight the Target

The target must be Linux with eBPF support. Linux 5.8 or newer is recommended;
5.1 has reduced feature coverage and 4.18 relies on compatibility behavior.

```bash
uname -r
test -e /sys/kernel/btf/vmlinux && echo "BTF available"
zgrep BPF /proc/config.gz
gcc --version
clang --version
cmake --version
pkg-config --modversion libbpf
bpftool version
```

Require a CMake version compatible with the repository's `3.20` minimum, GCC
11.2 or newer, Clang/LLVM 10 or newer, libbpf 1.5 or newer, and bpftool 7.5 or
newer. Ensure the kernel provides `CONFIG_BPF`, `CONFIG_BPF_SYSCALL`,
`CONFIG_BPF_JIT`, `CONFIG_HAVE_EBPF_JIT`, `CONFIG_BPF_EVENTS`, and
`CONFIG_DEBUG_INFO_BTF`. If BTF or automatic kernel-header detection is absent,
provide `DATACRUMBS_KERNEL_HEADERS_PATH`.

Install or expose the required development packages before configuring:
libbpf, libelf, zlib, OpenSSL, json-c, yaml-cpp, CMake, Make/Ninja, Git, and
pkg-config. `datacrumbs-utils` uses yaml-cpp even though the runtime does not.
Use `BPFTOOL_EXECUTABLE` when the required bpftool is not on `PATH`.

## 2. Configure, Build, and Install

Configure the core runtime from the repository root. Install the separately
distributed `datacrumbs-utils` package into the same prefix before attempting
probe generation or workload wrapping: it provides `datacrumbs_probe_configurator`,
`datacrumbs_wrap`, `libdatacrumbs_client.so`, and install-time runtime data.
For local development, use a user-writable prefix:

```bash
cmake -S . -B build \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local/datacrumbs" \
  -DDATACRUMBS_HOST="$(hostname -s)" \
  -DDATACRUMBS_USER="$USER" \
  -DDATACRUMBS_INSTALL_USER="$USER" \
  -DDATACRUMBS_SCHEDULER_TYPE=NONE \
  -DDATACRUMBS_SCHEDULER_JOBID_ENV_VAR=DATACRUMBS_LOCAL_RUN_ID
cmake --build build --parallel
cmake --install build
```

For production, choose a shared prefix such as `/opt/datacrumbs`, configure the
site runtime user, scheduler, trace/log/run directories, and run
`sudo cmake --install build`. Then install the matching utilities package into
that exact prefix. A user-prefix build is not a production eBPF deployment.
Pass only needed tuning options, for example
`-DDATACRUMBS_TRACE_RINGBUF_SIZE_MB=...`,
`-DDATACRUMBS_MAX_RUNTIME_FUNCTIONS=...`, `-DDATACRUMBS_MODE_STR=TRACE`, or
`-DDATACRUMBS_KERNEL_HEADERS_PATH=...`.

The install must produce at least:

```bash
test -x /opt/datacrumbs/sbin/datacrumbs
test -x /opt/datacrumbs/sbin/datacrumbs_probe_manager
test -f /opt/datacrumbs/etc/datacrumbs/systemd/datacrumbs@.service
test -f /opt/datacrumbs/etc/datacrumbs/systemd/datacrumbs_probe_manager.service
sudo stat -c '%a %U:%G %n' /opt/datacrumbs/share/datacrumbs/data/.datacrumbs-probe-secret
```

The probe secret should remain root-owned and mode `0600`; never broaden it for
users or copy it into user homes.

## 3. Deploy by Node Role

On each compute node, register the runtime template:

```bash
sudo ln -sf /opt/datacrumbs/etc/datacrumbs/systemd/datacrumbs@.service \
  /etc/systemd/system/datacrumbs@.service
sudo systemctl daemon-reload
```

On each login node where users generate probe files, register and start the
trusted probe manager before running `datacrumbs_probe_configurator`:

```bash
sudo ln -sf /opt/datacrumbs/etc/datacrumbs/systemd/datacrumbs_probe_manager.service \
  /etc/systemd/system/datacrumbs_probe_manager.service
sudo systemctl daemon-reload
sudo systemctl enable --now datacrumbs_probe_manager.service
sudo systemctl status datacrumbs_probe_manager.service
```

For production Flux or SLURM, also install the scheduler-specific prolog and
epilog integration. Jobs must carry the signed `probe_file` metadata; the prolog
starts `datacrumbs@<job-id>.service` and the epilog stops it. For an isolated
test, use `datacrumbs_service_wrapper start|stop` or invoke `datacrumbs` directly
with a signed probes file. The older server-run/server-stop and composable flows
are unsupported.

## 4. Account for Privileges and Limits

- The runtime `datacrumbs@.service` and probe-manager service explicitly run as
  `root`; this is the supported deployment model for eBPF loading and access to
  the signing secret.
- Check `cat /proc/sys/kernel/unprivileged_bpf_disabled`. Do not enable
  unprivileged BPF merely to work around service setup. The documentation notes
  that a distribution may expose a `bpf` group, but this repository does not
  prescribe a group or capability-only deployment.
- No udev rules are supplied or documented. Do not invent device permissions;
  investigate site security policy, SELinux/AppArmor, or container restrictions
  only if BPF loading fails under the root service.
- Startup raises `RLIMIT_NOFILE`, `RLIMIT_AS`, and `RLIMIT_MEMLOCK` only from
  their soft values to their current hard values. Confirm the hard ceilings are
  sufficient with `systemctl show`, PAM limits, or site policy. When site policy
  permits it, add a service drop-in for the runtime template:

  ```bash
  sudo systemctl edit datacrumbs@.service
  ```

  ```ini
  [Service]
  LimitNOFILE=65536
  LimitMEMLOCK=infinity
  ```

  Then run `sudo systemctl daemon-reload`. Select final limit values with the
  site administrator; `infinity` is not appropriate where locked-memory limits
  are intentionally constrained.
- Ensure the configured log, trace, and run directories can be created and
  written by the root service. The service changes generated log ownership to
  the configured DataCrumbs user and mode `0660`.
- Keep the probe manager endpoint restricted to its intended login-node network
  boundary. The configured default TCP port is `43123`; avoid exposing it beyond
  the trusted environment without a reviewed network policy.

## 5. Validate the Installed Deployment

Run the checks appropriate to the deployment level:

```bash
sudo systemctl status datacrumbs_probe_manager.service
sudo systemctl cat datacrumbs@.service
sudo journalctl -u datacrumbs_probe_manager.service -b --no-pager
ulimit -n
ulimit -l
```

Then generate a signed probe document through the installed configurator and
run a single-node or scheduler-controlled test job. Confirm the runtime reaches
its ready file under the configured run directory, attaches the expected probes,
writes traces and logs to the configured locations, and exits cleanly when the
service is stopped. Investigate systemd logs and the runtime-status SQLite file
before retrying a failed probe target because known failures are skipped later.

## Reference Sources

Use the repository documentation for scheduler-specific configuration and
package examples:

- [Build guide](../../../docs/build.rst)
- [Dependencies](../../../docs/dependencies.rst)
- [Runtime setup](../../../docs/setup.rst)
- [HPC deployment](../../../docs/deployment.rst)
- [Flux integration](../../../docs/flux_integration.rst)
- [SLURM integration](../../../docs/slurm_integration.rst)