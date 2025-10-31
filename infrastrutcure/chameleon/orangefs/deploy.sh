#!/bin/bash
set -u
set -e
#Remeber to have env Variables for:
# ORANGEFS_KO
# ORANGEFS_PATH
# PVFS2TAB_FILE

CWD=$(pwd)

if [ $# -eq 0 ]; then
  echo "$(basename $0) <server list> <client list>"
  echo "OR\n$(basename $0) <server list> <client list> <conf file> <mount_loc>"
  exit 0
fi

server_loc=${1}
client_loc=$2
conf_file=${ORANGEFS_CONFIG:-$3}
client_dir=${ORANGEFS_MOUNT:-$4}

#Input Variables
server_dir=$(awk '$1 ~ /DataStorageSpace/ {print $2}' $conf_file)
meta_dir=$(awk '$1 ~ /MetadataStorageSpace/ {print $2}' $conf_file)

#General Variables
server_list=($(cat $server_loc))
client_list=($(cat $client_loc))

#Config PFS
name=$(grep -oP '(?<=Name )\w+' "${conf_file}" | head -n 1)        #TODO: Allow renaming
comm_port=$(grep -oP 'tcp://[^:]+:\K\d+' ${conf_file} | head -n 1) #TODO: Allow changing
OFS_PATH=$ORANGEFS_PATH

echo "Setting up ${name} on port ${comm_port}"

echo $CWD
count=0

set -x
set +e

OFS_LMOD="orangefs/2.10.0"

#echo "Setting up servers"
#echo "Cleanup (Can Fail if nothing to clean)"
#parallel-ssh -h ${server_loc} "killall pvfs2-server"
#parallel-ssh -h ${server_loc} "rm -rf ${server_dir}"
#parallel-ssh -h ${server_loc} "rm -rf ${meta_dir}"
echo "Deployment"
parallel-ssh -h "${server_loc}" -i \
  "mkdir -p '${server_dir}' && \
	mkdir -p '${meta_dir}' && \
	${OFS_PATH}/sbin/pvfs2-server -f -a \$(hostname) ${conf_file} && \
	${OFS_PATH}/sbin/pvfs2-server -a \$(hostname) ${conf_file}"

#parallel-ssh -h ${server_loc} "mkdir -p ${server_dir}"
#parallel-ssh -h ${server_loc} "mkdir -p ${meta_dir}"
#parallel-ssh -h ${server_loc} "${ORANGEFS_PATH}/sbin/pvfs2-server -f -a "'$(hostname)'" ${conf_file}"
#parallel-ssh -h ${server_loc} "${ORANGEFS_PATH}/sbin/pvfs2-server -a "'$(hostname)'" ${conf_file}"
echo "Report"
parallel-ssh -h ${server_loc} -i "(ps -aef | grep pvfs2 | grep -v grep) || echo 'Server deployment correct'"

echo "\nStarting clients"
echo "Cleanup (Can Fail if nothing to clean)"
parallel-ssh -h ${client_loc} "sudo umount -t pvfs2 ${client_dir}"
parallel-ssh -h ${client_loc} "sudo kill-pvfs2-client"
parallel-ssh -h ${client_loc} "sudo rmmod orangefs"
echo "Deployment"

parallel-ssh -h "${client_loc}" -i \
  "mkdir -p '${client_dir}' && \
	sudo /home/cc/datacrumbs/infrastrutcure/chameleon/orangefs/orangefs_client_mount.sh && \
	sudo mount -t pvfs2 tcp://${server_list[0]}:${comm_port}/${name} '${client_dir}'"

#sudo modprobe orangefs && \
#sudo /usr/bin/bash -lc \'. /etc/profile.d/lmod.sh\' && \
#sudo /usr/bin/bash -lc \'module load orangefs/2.10\' && \
#sudo /usr/bin/bash -lc \'${ORANGEFS_PATH}/sbin/pvfs2-client -p ${ORANGEFS_PATH}/sbin/pvfs2-client-core\' && \

#parallel-ssh -h ${client_loc} "mkdir -p ${client_dir}"
#parallel-ssh -h ${client_loc} "sudo modprobe orangefs"
#parallel-ssh -h ${client_loc} "sudo . /etc/profile.d/lmod.sh && module load ${OFS_LMOD} &&  ${ORANGEFS_PATH}/sbin/pvfs2-client -p ${ORANGEFS_PATH}/sbin/pvfs2-client-core"
#parallel-ssh -h ${client_loc} "sudo mount -t pvfs2 tcp://${server_list[0]}:${comm_port}/${name} ${client_dir}"
echo "Report"
parallel-ssh -h ${client_loc} -i "(ps -aef | grep pvfs2 | grep -v grep) || echo 'Client kill correct'"
parallel-ssh -h ${client_loc} -i "(mount | grep pvfs2) || echo 'Umount correct'"
parallel-ssh -h ${client_loc} -i "(lsmod | grep orangefs) || echo 'Kmod removed correct'"
