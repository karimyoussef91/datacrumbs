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

## Memory and I/O Data-Operation Roofline

The staged implementation in `roofline_research_context.md` has three new
scripts:

- `scripts/derive_dataop_memory_io_ceilings.py` reads the existing STREAM and
	IOR ceiling CSVs and writes the combined ceiling schema with provenance.
- `scripts/generate_dataop_roofline.py` converts measured memory and I/O
	bandwidths into effective ceilings using
	`effective_bandwidth = raw_bandwidth / traffic_amplification`.
- `scripts/analyze_dataop_roofline_dftracer.py` uses
	`dftracer.utils.TraceViewer`, `Field.is_in()`, `agg("count", "sum:dur")`,
	`collect()`, and `to_pandas()` to derive three trace timing views.
- `scripts/plot_dataop_roofline.py` plots the two effective resource lines,
	the measured DataOp-rate ceiling, their lower envelope, and trace points.

All three points use one declared logical work definition and common logical
byte denominator:

```text
data_intensity = logical_dataops / logical_bytes
point_rate = logical_dataops / layer_duration
```

The default logical DataOp is one traced MPI-IO data-transfer call. The three
timing views are memory syscalls, MPI-IO, and POSIX I/O. Communication is
intentionally deferred until its bandwidth and traffic are measured.
Their native event counts are exported for auditing but are not substituted
for the common logical DataOp count. HDF5 can be selected with
`--dataop-events` when a trace actually contains HDF5 operations.

Generate points from the current trace:

```bash
/home/cc/dftracer-utils-develop/.dftracer_venv/bin/python3 \
	scripts/analyze_dataop_roofline_dftracer.py \
	--logical-bytes 33554432
```

Generate ceilings only after measuring all required inputs:

```bash
# Raw benchmark references (alpha=1 is explicit, not claimed as measured)
python3 scripts/derive_dataop_memory_io_ceilings.py

# Application-effective ceilings when traffic measurements are available
python3 scripts/derive_dataop_memory_io_ceilings.py \
	--logical-bytes <Q_D> \
	--memory-traffic-bytes <Q_M> \
	--io-traffic-bytes <Q_IO>

python3 scripts/plot_dataop_roofline.py
```

The current raw-reference derivation reads `data/memory.csv` and
`data/io_roofline_system.csv` and produces:

```text
memory bandwidth = 144.973786 GB/s
I/O bandwidth    = 70.381648 GB/s
operation roof   = 989320 POSIX IOPS/s (provisional semantic reference)
```

The resulting CSV is `data/dataop_memory_io_ceilings.csv`, and the rendered
figure is `dataop_memory_io_roofline.png`.

Alternatively, generate the same schema directly from explicit measurements:

```bash
python3 scripts/generate_dataop_roofline.py \
	--logical-bytes <Q_D> \
	--dataops-peak <measured-DataOps-per-second> \
	--memory-bandwidth-gbs <measured-GB-per-second> \
	--memory-traffic-bytes <Q_M> \
	--io-bandwidth-gbs <measured-GB-per-second> \
	--io-traffic-bytes <Q_IO>
```

The existing data provide DRAM and storage bandwidth benchmarks, but not the
application's memory/I/O traffic or a logical DataOp-rate benchmark. The
generator therefore requires these values explicitly and never assumes traffic
amplification is one. Cumulative trace durations may overlap across ranks and
layers; use the layer-specific `--*-seconds` options when a validated wall or
active interval is available.