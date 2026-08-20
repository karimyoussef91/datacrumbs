#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_dir="${root_dir}/data"
target_dir=${1:-"${data_dir}/io_roofline"}
ior_bin=${IOR_BIN:-"$HOME/.local/ior/bin/ior"}
mkdir -p "${data_dir}" "${target_dir}"

if [[ ! -x "${ior_bin}" ]]; then
  echo "IOR binary not found at ${ior_bin}; set IOR_BIN or install IOR" >&2
  exit 1
fi

# Use all physical cores across both sockets, matching the CPU/memory roofline scripts.
physical_cpus=$(lscpu -p=CPU,CORE,SOCKET | awk -F, '!/^#/ && !seen[$2 ":" $3]++ {printf "%s%s", separator, $1; separator=","}')
physical_threads=$(awk -F, '{print NF}' <<<"${physical_cpus}")

iops_log="${data_dir}/io_roofline_iops_run.txt"
bandwidth_log="${data_dir}/io_roofline_bandwidth_run.txt"

# Peak IOPS (psi): small transfers, high parallelism, file-per-process.
mpirun -np "${physical_threads}" --bind-to core "${ior_bin}" \
  -a POSIX -b 4k -t 4k -s 100 -F -w -r -e -o "${target_dir}/ior-iops" > "${iops_log}"

# Peak I/O bandwidth (kappa): large sequential transfers.
mpirun -np "${physical_threads}" --bind-to core "${ior_bin}" \
  -a POSIX -b 4m -t 4m -s 20 -F -w -r -e -o "${target_dir}/ior-bandwidth" > "${bandwidth_log}"

python3 - "${iops_log}" "${bandwidth_log}" "${data_dir}/io_roofline_system.csv" <<'PY'
import csv
import re
import sys

iops_log_path, bandwidth_log_path, output_path = sys.argv[1:]

row_pattern = re.compile(r"^(write|read)\s+([\d.]+)\s+([\d.]+)\s")


def parse(path):
    bandwidths_mibs = []
    iops_values = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            match = row_pattern.match(line)
            if match:
                bandwidths_mibs.append(float(match.group(2)))
                iops_values.append(float(match.group(3)))
    return bandwidths_mibs, iops_values


iops_run_bw, iops_run_iops = parse(iops_log_path)
bandwidth_run_bw, bandwidth_run_iops = parse(bandwidth_log_path)

peak_iops = max(iops_run_iops + bandwidth_run_iops)
peak_bandwidth_mibs = max(iops_run_bw + bandwidth_run_bw)
peak_bandwidth_gbs = peak_bandwidth_mibs * 1024 * 1024 / 1.0e9

with open(output_path, "w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["metric", "value", "unit"])
    writer.writerow(["peak_iops", f"{peak_iops:.6f}", "IOP/s"])
    writer.writerow(["peak_bandwidth", f"{peak_bandwidth_gbs:.6f}", "GB/s"])

print(f"peak_iops={peak_iops:.2f} IOP/s")
print(f"peak_bandwidth={peak_bandwidth_gbs:.6f} GB/s")
PY
