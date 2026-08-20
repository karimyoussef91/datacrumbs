#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_dir="${root_dir}/data"
binary="${root_dir}/bin/stream_triad"
mkdir -p "${data_dir}" "$(dirname "${binary}")"

physical_cpus=$(lscpu -p=CPU,CORE,SOCKET | awk -F, '!/^#/ && !seen[$2 ":" $3]++ {printf "%s%s", separator, $1; separator=","}')
physical_threads=$(awk -F, '{print NF}' <<<"${physical_cpus}")
available_kib=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
elements=$((available_kib * 1024 / 48))
minimum_elements=16000000
maximum_elements=100000000
if (( elements < minimum_elements )); then elements=${minimum_elements}; fi
if (( elements > maximum_elements )); then elements=${maximum_elements}; fi

gcc -O3 -march=native -ffast-math -fopenmp "${root_dir}/src/stream_triad.c" -o "${binary}"
OMP_NUM_THREADS="${physical_threads}" OMP_PROC_BIND=close OMP_PLACES=cores \
  taskset -c "${physical_cpus}" "${binary}" "${elements}" > "${data_dir}/memory_stream.txt"

bandwidth_gbs=$(awk -F= '/^bandwidth_gbs=/{print $2}' "${data_dir}/memory_stream.txt")
printf 'metric,value,unit\ndram_bandwidth,%.6f,GB/s\n' "${bandwidth_gbs}" > "${data_dir}/memory.csv"
printf 'STREAM Triad: %s GB/s using %s physical cores and %s elements\n' \
  "${bandwidth_gbs}" "${physical_threads}" "${elements}"