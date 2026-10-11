#!/usr/bin/env bash
source "$(dirname "$0")/env.sh"
mapred --daemon stop historyserver || true
yarn --daemon stop nodemanager || true
yarn --daemon stop resourcemanager || true
hdfs --daemon stop datanode || true
hdfs --daemon stop namenode || true
