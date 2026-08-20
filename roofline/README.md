# Local Roofline Measurements

This directory measures and plots a node-level roofline model from local
benchmarks. It produces four ceilings:

- measured double-precision FMA compute peak;
- sustainable DRAM bandwidth from STREAM Triad;
- direct-I/O sequential storage read bandwidth;
- direct-I/O sequential storage write bandwidth.

The storage lines are plotted as a scale of the measured DRAM roof:

$$\alpha_{storage} = \frac{B_{storage}}{B_{DRAM}}$$

On a true NVMe node, `run_nvme_roofline.sh` records `storage_class=nvme`. The
script does not pretend another device is NVMe: it records the backing device
model and class in `data/storage.csv`. This current host's root filesystem is
on a non-NVMe SATA SSD, so its resulting storage ceilings are labelled as such.

## Run

```bash
./scripts/run_cpu_roofline.sh
./scripts/run_memory_roofline.sh
./scripts/run_nvme_roofline.sh "$PWD/data/io"
python3 scripts/plot_roofline.py
```

The scripts write benchmark data under `data/` and the plot to
`roofline_model.png`. `run_nvme_roofline.sh` uses `fio --direct=1`, so it avoids
the page cache. Its temporary test file is deleted after the read measurement.

To measure a different storage mount, pass that mount directory as the first
argument to `run_nvme_roofline.sh`. Do not point it at a production filesystem
without confirming that the temporary `fio-roofline.bin` path is acceptable.

## Interpretation

The plot uses operational intensity in FLOP/byte on the horizontal axis and
performance in GFLOP/s on the vertical axis. The bandwidth roof for a level is

$$P(I) = I \times B$$

where $B$ is in GB/s. The horizontal compute line is the measured FMA peak.
Storage roofs are out-of-core ceilings and are not substitutes for DRAM roofs
for in-memory workloads. Random/small I/O is latency and IOPS limited and is
outside this bandwidth roofline model.

## IOR Trace Layers

Analyze the generated two-rank IOR trace with its explicit path:

```bash
python3 scripts/analyze_ior_trace.py \
	--trace /home/cc/traces/26/08/20/trace-cc-mpi-ior-2rank-linked-xio-rooflines-ior-mpi-syscalls.pfw.gz
```

This current trace is a syscall-only trace from `IOR -a POSIX`. It can report
POSIX call counts and cumulative durations, but it cannot create valid
FLOP/byte roofline points by itself: IOR has no FLOP count, syscall arguments
do not include byte counts, and there is no MPI-IO layer in a POSIX IOR run.
The analyzer writes its observations to `data/ior_trace_analysis.json` and
`data/ior_trace_layers.csv` without fabricating missing measurements.

For the bundled trace only, the analyzer also knows the recorded two-rank IOR
phase metadata: 16 MiB written in `0.050916` seconds and 16 MiB read in
`0.002455` seconds. It writes two **I/O throughput** layer points to
`data/ior_io_layer_points.csv`: the end-to-end IOR application throughput and
the workload bytes divided by the cumulative POSIX syscall duration. These use
GB/s, not GFLOP/s, and appear in the `IOR stack points` inset when
`plot_roofline.py` runs. The POSIX point is overhead-inclusive because the
trace also captures loader and runtime syscalls.

To compare these two I/O points without the roofline's logarithmic axes or
inset, generate the dedicated linear figure:

```bash
python3 scripts/plot_ior_stack.py --output ior_stack_linear.png
```

For an application with a measured FLOP count and an MPI-IO-instrumented run,
provide consistent data volume and wall-clock intervals to generate layer
markers and overlay them on the roofline:

```bash
python3 scripts/analyze_ior_trace.py \
	--trace /path/to/mpiio-trace.pfw.gz \
	--application-flops <flops> \
	--workload-bytes <bytes> \
	--application-seconds <application-wall-seconds> \
	--mpiio-seconds <mpiio-wall-seconds> \
	--posix-seconds <posix-wall-seconds>

python3 scripts/plot_roofline.py \
	--points data/ior_roofline_points.csv \
	--output roofline_with_trace_points.png
```

## I/O Roofline (IOPS vs. I/O Operational Intensity)

This model follows Zhu & Neuwirth (ICPADS'23): attainable performance is
`min(peak_iops, peak_bandwidth * IOI)`, where I/O operational intensity
`IOI = theta / sigma` (traced I/O operations per byte moved), plotted on IOPS
vs. IOP/byte axes instead of GFLOP/s vs. FLOP/byte. `peak_iops`/`peak_bandwidth`
are system-specific (from an IOR sweep); `IOI` and per-layer IOPS are
application-specific (from the DataCrumbs trace).

```bash
# 1. Derive peak IOPS (psi) and peak bandwidth (kappa) via IOR, plot roofline only
bash scripts/run_io_roofline_benchmark.sh
python3 scripts/plot_io_roofline.py --output io_roofline_model.png

# 2. Derive application/POSIX IOPS-vs-IOI points from the bundled trace
python3 scripts/analyze_io_roofline.py

# 3. Plot the roofline with the derived points overlaid
python3 scripts/plot_io_roofline.py \
	--points data/io_roofline_points.csv \
	--output io_roofline_with_points.png
```

`run_io_roofline_benchmark.sh` uses `mpirun` with IOR's own reported IOPS
column (no `--direct`), so `peak_iops` reflects page-cache-assisted small-I/O
performance, not raw-device IOPS; the `fio --direct=1` results in
`data/storage.csv` remain the honest device-level bandwidth ceiling.
`analyze_io_roofline.py` reports both `overall_application` (wall-clock IOPS)
and `posix` (cumulative-syscall-time IOPS, overhead-inclusive) at the same
`IOI`, since both share the same traced operation count and byte total. An
`mpi_io` point requires an `IOR -a MPIIO` trace with MPI-IO events; the
bundled `-a POSIX` trace has none, and the script reports this instead of
fabricating a value.