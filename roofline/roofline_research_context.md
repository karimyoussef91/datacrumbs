# Unified Data-Operation Roofline: Research and Implementation Context

## 1. Research Objective

The goal is to develop a unified performance model for data-intensive
HPC applications that extends Roofline reasoning across the data path,
including:

-   memory,
-   network communication,
-   storage,
-   and software-stack layers such as HDF5, MPI-IO, and POSIX.

The central abstraction is to replace FLOPs (classical Roofline) or
storage-specific IOPS (I/O Roofline) with a generalized **Data Operation
(DataOp)**.

The model should answer two related questions:

1.  **Bounding:** What resource limits the attainable rate of useful
    data operations?
2.  **Explainability:** Why is the observed application or
    software-layer performance below that bound?

The implementation will use deep traces, including DataCrumbs/Perfetto
traces, to derive application behavior and software-stack measurements.
A later explainability component can use knowledge synthesis to
characterize gaps as inherent/system-imposed versus
implementation/configuration-related.

------------------------------------------------------------------------

## 2. Literature Background

### 2.1 Classical Roofline

The classical Roofline model expresses attainable floating-point
performance as

\[ P\_{`\mathrm{FLOP}`{=tex}} = `\min`{=tex}`\left`{=tex}(
P\_{`\mathrm{FLOP}`{=tex}}\^{peak}, B_M I_A `\right`{=tex}) \]

where

\[ I_A = `\frac{\mathrm{FLOPs}}`{=tex} {`\mathrm{memory\ bytes}`{=tex}}
\]

is arithmetic/operational intensity and (B_M) is sustainable memory
bandwidth.

Conceptually, Roofline relates:

\[ `\text{work rate}`{=tex} `\le`{=tex} `\min`{=tex}(
`\text{operation-rate ceiling}`{=tex}, `\text{bandwidth}`{=tex}
`\times `{=tex}`\text{work/byte}`{=tex} ). \]

This work-versus-traffic abstraction is the foundation for the
generalized model.

### 2.2 Communication-Aware Roofline

Communication-aware Roofline extends Roofline reasoning to
distributed-memory communication using

\[ I_N = `\frac{\mathrm{FLOPs}}`{=tex} {`\mathrm{network\ bytes}`{=tex}}
\]

and

\[ P = `\min`{=tex}`\left`{=tex}( P\_{`\mathrm{FLOP}`{=tex}}\^{peak},
B_N I_N `\right`{=tex}). \]

An important limitation identified in this literature is that memory
operational intensity and communication intensity have different byte
denominators. Consequently, simply adding a network line to a
conventional 2-D Roofline is not generally sufficient.

### 2.3 Ridgeline

Ridgeline addresses compute, memory, and network limits in a planar
representation.

Its quantities include:

\[ I_A = `\frac{F}{B_M}`{=tex}, \]

\[ I_M = `\frac{B_M}{B_N}`{=tex}, \]

and

\[ I_N = `\frac{F}{B_N}`{=tex}. \]

Here:

-   (F): FLOPs per work unit,
-   (B_M): memory bytes per work unit,
-   (B_N): network bytes per work unit.

Ridgeline demonstrates that multiple resource bottlenecks can be
combined into a meaningful 2-D representation when the relationships
among their intensity measures are explicitly modeled.

### 2.4 I/O Roofline

The empirical I/O Roofline replaces FLOPs with I/O operations.

Its attainable performance is

\[ P\_{`\mathrm{IO}`{=tex}} = `\min`{=tex}`\left`{=tex}(
P\_{`\mathrm{IOPS}`{=tex}}\^{peak}, B_S I\_{`\mathrm{IO}`{=tex}}
`\right`{=tex}), \]

where

\[ I\_{`\mathrm{IO}`{=tex}} = `\frac{\mathrm{I/O\ operations}}`{=tex}
{`\mathrm{bytes\ transferred}`{=tex}}. \]

The model uses empirical benchmarks such as IOR to derive storage
bandwidth and IOPS ceilings.

It can construct separate Rooflines for interfaces such as POSIX and
MPI-IO because operation counts and attainable performance may differ
across software interfaces.

### 2.5 Generalized I/O Operations

Recent I/O Roofline work for heterogeneous storage access broadens the
meaning of an operation beyond conventional POSIX I/O. Actions such as
read, write, put, get, and copy can be treated as abstract I/O
operations.

This motivates using a more general **DataOp** as the unit of useful
work.

------------------------------------------------------------------------

## 3. Proposed Unified Data-Operation Model

### 3.1 Logical Work

Define

\[ W = `\text{number of logical DataOps}`{=tex}. \]

The observed DataOp performance is

\[ P_D = `\frac{W}{T}`{=tex} \]

with units

\[ \[`\mathrm{DataOps/s}`{=tex}\]. \]

A DataOp represents useful logical data-access work rather than a
hardware transaction.

The precise DataOp semantics must be explicitly defined for each
experiment. Candidate operations include:

-   application-level data accesses,
-   HDF5 reads/writes,
-   object get/put operations,
-   logical dataset accesses.

Avoid silently equating a logical DataOp with every low-level request
generated below it.

------------------------------------------------------------------------

## 4. Canonical Data Intensity

Let

\[ Q_D = `\text{logical data bytes requested by the application}`{=tex}.
\]

Define the common x-axis quantity

\[ `\boxed{
I_D =
\frac{W}{Q_D}
}`{=tex} \]

with units

\[ \[`\mathrm{DataOps/byte}`{=tex}\]. \]

This is the **Data Intensity**.

The intended 2-D graph is therefore:

-   **x-axis:** Data Intensity, DataOps/logical byte
-   **y-axis:** Data Operation Rate, DataOps/s

Using logical application bytes as the canonical denominator is
important because memory, network, and storage may move different
physical byte volumes for the same logical application request.

------------------------------------------------------------------------

## 5. Resource Traffic

For each resource (r), measure the actual bytes crossing that resource:

\[ Q_M = `\text{memory traffic}`{=tex}, \]

\[ Q_N = `\text{network traffic}`{=tex}, \]

\[ Q_S = `\text{storage traffic}`{=tex}. \]

Resource-specific intensities are

\[ I_M = `\frac{W}{Q_M}`{=tex}, \]

\[ I_N = `\frac{W}{Q_N}`{=tex}, \]

\[ I_S = `\frac{W}{Q_S}`{=tex}. \]

Without normalization, these are different x-axis quantities and
therefore should not simply be treated as one common "operations/byte"
coordinate.

------------------------------------------------------------------------

## 6. Traffic Amplification

Define a resource-specific **traffic amplification factor**

\[ `\boxed{
\alpha_r =
\frac{Q_r}{Q_D}
}`{=tex} \]

for

\[ r `\in `{=tex}{M,N,S}. \]

Therefore,

\[ Q_r = `\alpha`{=tex}\_r Q_D. \]

The corresponding resource-specific intensity becomes

\[ I_r = `\frac{W}{Q_r}`{=tex} = `\frac{W}{\alpha_r Q_D}`{=tex} =
`\frac{I_D}{\alpha_r}`{=tex}. \]

Traffic amplification has a physical interpretation:

> How many bytes cross a particular system resource for each logical
> application byte?

Examples:

\[ `\alpha`{=tex}\_S = 1 \]

means one physical storage byte is transferred per logical byte, whereas

\[ `\alpha`{=tex}\_S = 2.5 \]

means every logical byte causes 2.5 bytes of storage traffic.

The same reasoning applies to memory and network traffic.

------------------------------------------------------------------------

## 7. Effective Resource Bandwidth

Let the measured sustainable bandwidth of resource (r) be

\[ B_r. \]

The corresponding DataOp bound is

\[ P_r = B_r I_r. \]

Substituting

\[ I_r = `\frac{I_D}{\alpha_r}`{=tex} \]

gives

\[ P_r = `\frac{B_r}{\alpha_r}`{=tex}I_D. \]

Define

\[ `\boxed{
B_r^{eff}
=
\frac{B_r}{\alpha_r}.
}`{=tex} \]

Then

\[ `\boxed{
P_r(I_D)=B_r^{eff}I_D.
}`{=tex} \]

All resource ceilings can now be expressed against the same Data
Intensity axis.

------------------------------------------------------------------------

## 8. Unified Roofline Equation

The proposed generalized model is

\[ `\boxed{
P_{\max}(I_D)
=
\min
\left[
P_D^{peak},
B_M^{eff} I_D,
B_N^{eff} I_D,
B_S^{eff} I_D
\right].
}`{=tex} \]

Equivalently,

\[ `\boxed{
P_{\max}(I_D)
=
\min
\left[
P_D^{peak},
\frac{B_M}{\alpha_M}I_D,
\frac{B_N}{\alpha_N}I_D,
\frac{B_S}{\alpha_S}I_D
\right].
}`{=tex} \]

The terms correspond to:

-   (P_D\^{peak}): maximum sustainable DataOp rate,
-   (B_M/`\alpha`{=tex}\_M): effective memory bandwidth,
-   (B_N/`\alpha`{=tex}\_N): effective network bandwidth,
-   (B_S/`\alpha`{=tex}\_S): effective storage bandwidth.

The lowest active bound determines the predicted bottleneck.

------------------------------------------------------------------------

## 9. Computing the Raw Resource Ceilings

The ceilings should be empirically characterized using resource-specific
benchmarks, following classical and I/O Roofline methodology.

### 9.1 Memory Ceiling

Measure sustainable memory bandwidth:

\[ B_M\^{peak} = `\max`{=tex}
`\frac{\text{memory bytes moved}}{T}`{=tex}. \]

Candidate benchmark:

-   STREAM,
-   or a controlled memory-copy/read/write microbenchmark.

Where useful, hierarchical memory ceilings can be considered:

\[ B\_{L1}, B\_{L2}, B\_{L3}, B\_{`\mathrm{DRAM}`{=tex}}. \]

The primary model can initially use DRAM bandwidth.

### 9.2 Network Ceiling

Measure sustainable network bandwidth:

\[ B_N\^{peak} = `\max`{=tex}
`\frac{\text{network bytes transferred}}{T}`{=tex}. \]

Candidate benchmarks:

-   OSU Micro-Benchmarks,
-   MPI ping-pong,
-   MPI bandwidth tests.

If application communication is dominated by collectives, consider
measuring a collective-specific sustainable ceiling rather than assuming
point-to-point peak bandwidth represents all network behavior.

Possible distinction:

\[ B_N\^{p2p} \]

versus

\[ B_N\^{collective}. \]

### 9.3 Storage Ceiling

Measure sustainable storage bandwidth:

\[ B_S\^{peak} = `\max`{=tex}
`\frac{\text{storage bytes transferred}}{T}`{=tex}. \]

Candidate benchmarks:

-   IOR,
-   fio where appropriate,
-   storage/device-specific benchmarks.

The empirical I/O Roofline provides precedent for using IOR to derive
peak storage bandwidth and peak IOPS.

Separate interface-level empirical ceilings may also be useful:

\[ B\_{`\mathrm{POSIX}`{=tex}}, \]

\[ B\_{`\mathrm{MPIIO}`{=tex}}, \]

and possibly a lower-level filesystem/device ceiling.

### 9.4 DataOp-Rate Ceiling

The model should also include an operation-rate ceiling:

\[ `\boxed{
P_D^{peak}
=
\max
\frac{W}{T}.
}`{=tex} \]

This is analogous to:

-   peak FLOP/s in classical Roofline,
-   peak IOPS in I/O Roofline.

A custom microbenchmark can vary DataOp size over a wide range.

For small operations, performance should become operation-rate/latency
limited.

For large operations, performance should become bandwidth limited.

For a transfer size (S),

\[ `\mathrm{Ops/s}`{=tex} `\approx`{=tex} `\frac{B}{S}`{=tex} \]

when bandwidth is the dominant constraint.

------------------------------------------------------------------------

## 10. Raw Hardware vs. Effective Ceilings

Maintain a distinction between two concepts.

### 10.1 Raw/Sustainable Resource Ceiling

Measured independently using a resource-specific benchmark:

\[ B_M,`\quad `{=tex}B_N,`\quad `{=tex}B_S. \]

This answers:

> What rate can this subsystem sustain under controlled conditions?

### 10.2 Application-Effective Ceiling

Use traced traffic amplification:

\[ B_r\^{eff} = `\frac{B_r}{\alpha_r}`{=tex}. \]

This answers:

> Given the amount of physical traffic generated by this application's
> logical data movement, what useful logical-data rate can this resource
> support?

This distinction is important for explainability.

------------------------------------------------------------------------

## 11. Example

Suppose the application performs

\[ W=1000 `\mathrm{DataOps}`{=tex} \]

over

\[ Q_D=1 `\mathrm{GiB}`{=tex} \]

of logical application data.

Tracing reveals:

\[ Q_M=3 `\mathrm{GiB}`{=tex}, \]

\[ Q_N=1.2 `\mathrm{GiB}`{=tex}, \]

\[ Q_S=1.5 `\mathrm{GiB}`{=tex}. \]

Then

\[ `\alpha`{=tex}\_M=3, \]

\[ `\alpha`{=tex}\_N=1.2, \]

\[ `\alpha`{=tex}\_S=1.5. \]

If benchmarked sustainable bandwidths are

\[ B_M=120 `\mathrm{GB/s}`{=tex}, \]

\[ B_N=20 `\mathrm{GB/s}`{=tex}, \]

\[ B_S=12 `\mathrm{GB/s}`{=tex}, \]

then

\[ B_M\^{eff}=40 `\mathrm{GB/s}`{=tex}, \]

\[ B_N\^{eff}=16.67 `\mathrm{GB/s}`{=tex}, \]

\[ B_S\^{eff}=8 `\mathrm{GB/s}`{=tex}. \]

For this traffic pattern, storage gives the lowest effective bandwidth
and is therefore the first bandwidth bottleneck predicted by the model.

The numerical values in this section are illustrative, not measured
experimental results.

------------------------------------------------------------------------

## 12. DataCrumbs / Perfetto Integration

The implementation should derive as much application-specific behavior
as possible from deep tracing.

Conceptually:

``` text
Application
    |
    v
HDF5
    |
    v
MPI-IO
    |
    v
POSIX
    |
    v
OS / page cache / filesystem
    |
    +---- memory
    |
    +---- network
    |
    +---- storage
```

Useful quantities to extract include:

-   operation counts,
-   bytes requested,
-   bytes transferred,
-   operation duration,
-   concurrency,
-   request sizes,
-   read/write mix,
-   software layer,
-   temporal relationships between layers,
-   process/rank,
-   synchronization,
-   overlap where available.

External counters or tracing mechanisms may be necessary for resource
traffic not directly observable in the existing trace.

Do not infer memory/network/storage byte traffic from logical I/O bytes
unless the relationship has been validated.

------------------------------------------------------------------------

## 13. Software-Stack Points

A major research objective is to represent the application at multiple
software-stack layers rather than as a single point.

Candidate layers:

``` text
HDF5
  |
MPI-IO
  |
POSIX
  |
Filesystem / OS
  |
Hardware resources
```

For each layer (l), derive quantities such as

\[ W_l, \]

\[ Q_l, \]

\[ T_l, \]

and therefore

\[ I_l=`\frac{W_l}{Q_l}`{=tex}, \]

\[ P_l=`\frac{W_l}{T_l}`{=tex}. \]

Care is required because an "operation" at HDF5 is not necessarily
semantically equivalent to an operation at MPI-IO or POSIX.

The implementation should preserve both:

1.  native operation counts at each layer, and
2.  mappings to a common logical DataOp when such mappings can be
    established.

This distinction should not be hidden by normalization.

------------------------------------------------------------------------

## 14. Gap Decomposition

The model should ultimately distinguish several levels:

``` text
Raw resource ceiling
        |
        v
Sustainable benchmark ceiling
        |
        v
Application-effective ceiling
        |
        v
Software-stack attainable behavior
        |
        v
Observed application performance
```

Potential gaps include:

### Hardware/sustainable gap

Difference between theoretical hardware capability and empirically
sustainable benchmark performance.

### Traffic-amplification gap

Difference caused by

\[ `\alpha`{=tex}\_r \> 1. \]

Examples may include:

-   redundant movement,
-   buffering/copies,
-   protocol overhead,
-   filesystem behavior,
-   read/write amplification.

### Software-stack gap

Difference between the effective resource bound and performance attained
through HDF5/MPI-IO/POSIX.

Possible explanations include:

-   request granularity,
-   serialization,
-   collective I/O behavior,
-   synchronization,
-   metadata operations,
-   buffering,
-   configuration,
-   file layout,
-   insufficient concurrency.

### Application gap

Difference caused by application access patterns or implementation
choices.

The later knowledge-synthesis component should classify gaps into
categories such as:

-   inherent/system-imposed,
-   application implementation,
-   library configuration,
-   runtime/system configuration,
-   potentially optimizable,
-   insufficient evidence.

Avoid automatically labeling every gap as an optimization opportunity.

------------------------------------------------------------------------

## 15. Initial Plot Design

The initial unified plot should use log-log axes.

### X axis

``` text
Data Intensity [DataOps / logical byte]
```

### Y axis

``` text
Data Operation Rate [DataOps / s]
```

Plot:

-   DataOp-rate horizontal ceiling,
-   memory effective-bandwidth ceiling,
-   network effective-bandwidth ceiling,
-   storage effective-bandwidth ceiling,
-   measured application point(s),
-   software-stack points where their semantics are compatible with the
    chosen coordinate system.

For each resource:

\[ P_r(I_D)=B_r\^{eff}I_D. \]

The overall envelope is

\[ P\_{`\max`{=tex}}(I_D)= `\min`{=tex}\_r P_r(I_D) \]

including the horizontal DataOp ceiling.

Because bandwidth ceilings have slope 1 on a log-log plot, some resource
lines may lie entirely above others for fixed amplification factors.
Plot individual resource ceilings as well as the active lower envelope
so the user can inspect inactive constraints.

------------------------------------------------------------------------

## 16. Important Modeling Issue: Amplification May Not Be Constant

Do not assume

\[ `\alpha`{=tex}\_r \]

is globally constant.

It may depend on:

-   request size,
-   process count,
-   access pattern,
-   read versus write,
-   cache state,
-   HDF5 configuration,
-   MPI-IO configuration,
-   filesystem configuration,
-   concurrency,
-   collective behavior.

Therefore, consider

\[ `\alpha`{=tex}\_r = f(x) \]

where (x) represents workload/configuration parameters.

If amplification varies materially with Data Intensity, the
corresponding effective resource bound may not remain a simple straight
slope-one Roofline.

This should be tested empirically rather than assumed.

------------------------------------------------------------------------

## 17. Implementation Plan

### Phase 1 --- Trace Parser

Parse the Perfetto/DataCrumbs trace and produce a normalized event
representation.

Suggested fields:

``` python
event = {
    "timestamp": ...,
    "duration": ...,
    "layer": ...,
    "operation": ...,
    "bytes": ...,
    "rank": ...,
    "thread": ...,
    "read_write": ...,
}
```

### Phase 2 --- Per-Layer Metrics

Compute:

``` text
operation_count
bytes
active_time
wall_time
operation_rate
average_request_size
read_bytes
write_bytes
concurrency
```

for:

``` text
HDF5
MPI-IO
POSIX
```

### Phase 3 --- Existing I/O Roofline

First reproduce a conventional I/O Roofline:

\[ P\_{`\mathrm{IO}`{=tex}} = `\min`{=tex}(
P\_{`\mathrm{IOPS}`{=tex}}\^{peak}, B_S I\_{`\mathrm{IO}`{=tex}} ). \]

This provides a validation baseline.

### Phase 4 --- Resource Ceilings

Add benchmark-derived configuration:

``` yaml
ceilings:
  memory_bandwidth: ...
  network_bandwidth: ...
  storage_bandwidth: ...
  dataops_peak: ...
```

Keep benchmark values separate from application measurements.

### Phase 5 --- Traffic Amplification

Compute or ingest:

``` text
alpha_memory
alpha_network
alpha_storage
```

from measured traffic.

Then compute:

``` python
memory_effective_bw = memory_bw / alpha_memory
network_effective_bw = network_bw / alpha_network
storage_effective_bw = storage_bw / alpha_storage
```

### Phase 6 --- Unified Roofline

Implement

``` python
p_memory = memory_effective_bw * data_intensity
p_network = network_effective_bw * data_intensity
p_storage = storage_effective_bw * data_intensity

p_max = min(
    dataops_peak,
    p_memory,
    p_network,
    p_storage,
)
```

with consistent units.

### Phase 7 --- Software-Stack Visualization

Add HDF5, MPI-IO, and POSIX points.

Preserve the native metrics used to derive each point in the output data
so plotted values remain auditable.

### Phase 8 --- Gap Analysis

For each point, compute:

``` text
distance/rate ratio to active ceiling
active limiting resource
traffic amplification
gap to next software layer
```

These metrics will later feed the explainability system.

------------------------------------------------------------------------

## 18. Validation Strategy

The implementation should be validated incrementally.

### Validation A --- I/O Roofline reproduction

Check whether known IOR configurations reproduce the expected
relationship between:

-   transfer size,
-   IOPS,
-   bandwidth,
-   I/O intensity.

### Validation B --- Controlled bottlenecks

Construct workloads designed to be predominantly:

-   memory limited,
-   network limited,
-   storage limited,
-   operation-rate limited.

Verify that the model identifies the expected resource.

### Validation C --- Scaling

Vary:

-   node count,
-   rank count,
-   request size,
-   concurrency.

Determine whether benchmark ceilings and amplification factors remain
stable.

### Validation D --- Cross-layer consistency

For a traced logical request, verify mappings such as:

``` text
HDF5 operation
   -> MPI-IO operation(s)
      -> POSIX operation(s)
```

using timestamps, identifiers, call relationships, or other trace
information.

Do not assume a one-to-one mapping.

------------------------------------------------------------------------

## 19. Research Questions

Key questions that should remain explicit during implementation:

1.  What exactly constitutes one DataOp?
2.  Is a DataOp defined at the application level or independently at
    each layer?
3.  Can HDF5, MPI-IO, and POSIX points legitimately share one y-axis?
4.  What should be the canonical logical-byte denominator?
5.  How should metadata-only operations be represented?
6.  How should zero-byte synchronization operations be represented?
7.  Can memory traffic be measured accurately enough on the target
    system?
8.  Can network traffic be attributed to individual logical I/O
    operations?
9.  How should page-cache hits be represented when storage traffic is
    zero?
10. How should overlapping memory/network/storage activity affect the
    model?
11. Are traffic amplification factors approximately constant within a
    workload regime?
12. Should read and write Rooflines be separate?
13. Should network collectives and point-to-point communication have
    separate ceilings?
14. Should storage have POSIX, MPI-IO, filesystem, and device-level
    ceilings?
15. How should metadata-operation ceilings be modeled?
16. What constitutes an inherent gap versus an actionable performance
    gap?

------------------------------------------------------------------------

## 20. Current Core Hypothesis

The working hypothesis is:

> A data-intensive HPC application's attainable useful data-operation
> rate can be bounded in a common 2-D space by converting memory,
> network, and storage bandwidths into application-visible effective
> bandwidths using measured traffic amplification factors.

Formally:

\[ `\boxed{
P_{\max}(I_D)
=
\min
\left[
P_D^{peak},
\frac{B_M}{\alpha_M}I_D,
\frac{B_N}{\alpha_N}I_D,
\frac{B_S}{\alpha_S}I_D
\right].
}`{=tex} \]

The second hypothesis is:

> Deep tracing of the software and data-movement stack can explain why
> measured application and library-layer performance falls below these
> empirical ceilings.

These hypotheses should be treated as research hypotheses to validate,
not as assumptions that the implementation must force the data to
satisfy.

------------------------------------------------------------------------

## 21. Implementation Principles

When implementing this model:

-   Keep raw trace measurements separate from derived quantities.
-   Keep benchmark ceilings separate from application measurements.
-   Record units explicitly.
-   Never silently convert decimal GB to GiB or vice versa.
-   Preserve read/write distinction where available.
-   Preserve software-layer identity.
-   Preserve native operation semantics.
-   Make every plotted point reproducible from exported metrics.
-   Make every ceiling reproducible from benchmark data/configuration.
-   Treat traffic amplification as measured data, not a tuning
    parameter.
-   Do not introduce arbitrary scaling merely to make resource lines
    visually comparable.
-   Validate the conventional I/O Roofline before introducing the
    generalized model.
-   Prefer simple, auditable equations over increasingly complex
    normalization.
-   Flag missing measurements rather than estimating them without
    explicit justification.

------------------------------------------------------------------------

## 22. Terminology

Working terminology:

**Data Operation (DataOp)**\
A logical unit of useful data-access work.

**Data Operation Rate**\
\[ P_D=W/T \]

**Logical Data Volume**\
\[ Q_D \]

**Data Intensity**\
\[ I_D=W/Q_D \]

**Resource Traffic**\
\[ Q_r \]

**Traffic Amplification**\
\[ `\alpha`{=tex}\_r=Q_r/Q_D \]

**Sustainable Resource Bandwidth**\
\[ B_r \]

**Effective Resource Bandwidth**\
\[ B_r\^{eff}=B_r/`\alpha`{=tex}\_r \]

**Unified Data-Operation Roofline**\
\[ P\_{`\max`{=tex}}(I_D)= `\min`{=tex}`\left[
P_D^{peak},
B_M^{eff}I_D,
B_N^{eff}I_D,
B_S^{eff}I_D
\right]`{=tex}. \]

------------------------------------------------------------------------

## 23. Immediate Coding Goal

Start from the existing Perfetto/DataCrumbs trace parser.

The first implementation milestone should **not** attempt the entire
generalized model.

Implement in this order:

1.  robustly parse the real trace;
2.  identify HDF5, MPI-IO, and POSIX events;
3.  compute operation counts and byte volumes per layer;
4.  compute per-layer operation rates and intensities;
5.  generate a conventional I/O Roofline;
6.  validate results against manually inspected trace events;
7.  introduce benchmark ceiling configuration;
8.  add resource traffic/amplification only after the baseline is
    correct;
9.  generate the unified Data-Operation Roofline;
10. add gap characterization.

This staged approach keeps errors in trace interpretation from being
hidden by later modeling layers.
