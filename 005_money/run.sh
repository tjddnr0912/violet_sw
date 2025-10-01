#!/bin/bash
# Wrapper script to call the actual run.sh in 003_Execution_script/
cd "$(dirname "$0")"
exec ./003_Execution_script/run.sh "$@"
