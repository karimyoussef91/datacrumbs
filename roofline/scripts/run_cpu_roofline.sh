#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_dir="${root_dir}/data"
binary="${root_dir}/bin/fma_peak"
mkdir -p "${data_dir}" "$(dirname "${binary}")"

physical_cpus=$(lscpu -p=CPU,CORE,SOCKET | awk -F, '!/^#/ && !seen[$2 ":" $3]++ {printf "%s%s", separator, $1; separator=","}')
physical_threads=$(awk -F, '{print NF}' <<<"${physical_cpus}")

gcc -O3 -march=native -ffast-math -fopenmp "${root_dir}/src/fma_peak.c" -o "${binary}"
OMP_NUM_THREADS="${physical_threads}" OMP_PROC_BIND=close OMP_PLACES=cores \
  taskset -c "${physical_cpus}" "${binary}" > "${data_dir}/cpu_fma.txt"

gflops=$(awk -F= '/^gflops=/{print $2}' "${data_dir}/cpu_fma.txt")
printf 'metric,value,unit\ncompute_peak,%.6f,GFLOP/s\n' "${gflops}" > "${data_dir}/cpu.csv"
lscpu -J > "${data_dir}/lscpu.json"
printf 'CPU FMA peak: %s GFLOP/s using %s physical cores\n' "${gflops}" "${physical_threads}"