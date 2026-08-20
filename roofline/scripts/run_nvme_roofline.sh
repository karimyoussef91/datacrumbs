#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_dir="${root_dir}/data"
target_dir=${1:-"${data_dir}/io"}
file_size=${ROOFLINE_FIO_SIZE:-8G}
runtime_seconds=${ROOFLINE_FIO_RUNTIME_SECONDS:-30}
mkdir -p "${data_dir}" "${target_dir}"

if ! command -v fio >/dev/null 2>&1; then
  echo "fio is required; install it before running this script" >&2
  exit 1
fi

source_device=$(findmnt -no SOURCE -T "${target_dir}")
base_device=$(lsblk -no PKNAME "${source_device}" 2>/dev/null || true)
if [[ -z "${base_device}" ]]; then base_device=$(basename "${source_device}"); fi
device_path="/dev/${base_device}"
model=$(lsblk -dn -o MODEL "${device_path}" | xargs || true)
transport=$(lsblk -dn -o TRAN "${device_path}" | xargs || true)
if [[ "${base_device}" == nvme* ]]; then storage_class=nvme; else storage_class=non-nvme; fi

job_file="${target_dir}/fio-roofline.bin"
write_json="${data_dir}/storage_write.json"
read_json="${data_dir}/storage_read.json"
cleanup() { rm -f "${job_file}"; }
trap cleanup EXIT

fio --name=roofline-sequential-write --filename="${job_file}" --rw=write --bs=1M \
  --ioengine=io_uring --direct=1 --iodepth=32 --numjobs=1 --size="${file_size}" \
  --time_based --runtime="${runtime_seconds}" --group_reporting --eta=never --output-format=json \
  --output="${write_json}"
fio --name=roofline-sequential-read --filename="${job_file}" --rw=read --bs=1M \
  --ioengine=io_uring --direct=1 --iodepth=32 --numjobs=1 --size="${file_size}" \
  --time_based --runtime="${runtime_seconds}" --group_reporting --eta=never --output-format=json \
  --output="${read_json}"

python3 - "${write_json}" "${read_json}" "${data_dir}/storage.csv" \
  "${storage_class}" "${device_path}" "${model}" "${transport}" <<'PY'
import csv
import json
import sys

write_path, read_path, output_path, storage_class, device, model, transport = sys.argv[1:]

def bandwidth_gbs(path, operation):
    with open(path, encoding="utf-8") as stream:
        job = json.load(stream)["jobs"][0]
    return job[operation]["bw_bytes"] / 1.0e9

rows = [
    ("storage_read_bandwidth", bandwidth_gbs(read_path, "read")),
    ("storage_write_bandwidth", bandwidth_gbs(write_path, "write")),
]
with open(output_path, "w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["metric", "value", "unit", "storage_class", "device", "model", "transport"])
    for metric, value in rows:
        writer.writerow([metric, f"{value:.6f}", "GB/s", storage_class, device, model, transport])
for metric, value in rows:
    print(f"{metric}={value:.6f} GB/s")
print(f"storage_class={storage_class} device={device} model={model} transport={transport}")
PY