# Source this file:  source hadoop/env.sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export HADOOP_HOME=$HOME/opt/hadoop-3.5.0
export DELAYLENS_HOME=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
export HADOOP_CONF_DIR=$DELAYLENS_HOME/hadoop/conf
export HADOOP_LOG_DIR=$HOME/opt/hadoop-data/logs
export HADOOP_PID_DIR=$HOME/opt/hadoop-data/pids
export YARN_LOG_DIR=$HADOOP_LOG_DIR
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH
export HADOOP_STREAMING_JAR=$(ls $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar 2>/dev/null | head -1)
