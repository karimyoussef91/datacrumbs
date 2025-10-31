#!/bin/bash


modprobe orangefs 
source /etc/profile.d/lmod.sh
module load orangefs 
/opt/orangefs/2.10.0/sbin/pvfs2-client -p /opt/orangefs/2.10.0/sbin/pvfs2-client-core
