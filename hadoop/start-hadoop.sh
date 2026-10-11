#!/usr/bin/env bash
# Starts a single-node (pseudo-distributed) Hadoop cluster without SSH: HDFS + YARN + JobHistory.
set -euo pipefail
source "$(dirname "$0")/env.sh"
if [ ! -d "$HOME/opt/hadoop-data/namenode/current" ]; then
  hdfs namenode -format -force -nonInteractive
fi
hdfs --daemon start namenode
hdfs --daemon start datanode
yarn --daemon start resourcemanager
yarn --daemon start nodemanager
mapred --daemon start historyserver
sleep 5
hdfs dfsadmin -safemode wait
jps
echo "NameNode UI: http://localhost:9870   YARN UI: http://localhost:8088   JobHistory: http://localhost:19888"
