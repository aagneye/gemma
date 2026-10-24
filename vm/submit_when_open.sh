#!/usr/bin/env bash
# Retry a Kaggle code submission until the daily slot accepts it.
#   submit_when_open.sh <kernel> <version> "<message>" [not_before_utc, e.g. "2026-10-20 00:02"]
# Success is read from the submission list (the CLI's wording changed: success now prints "N submissions remaining today.").
K=$1; V=$2; M=$3; NB=${4:-}; R=/mnt/biohub/kdata/gemma4; C=gemma-4-developer-agent; source $R/.venv/bin/activate
LOG=$R/logs/kaggle_submit.log
if [ -n "$NB" ]; then t=$(date -u -d "$NB" +%s); while [ "$(date -u +%s)" -lt "$t" ]; do sleep 60; done; fi
listed() { kaggle competitions submissions $C 2>/dev/null | sed -n 3p | grep -qF "${M:0:50}"; }
while true; do
  out=$(kaggle competitions submit $C -k "$K" -f submission.zip -v "$V" -m "$M" 2>&1)
  echo "$(date -u) | $K v$V | $out" >> $LOG
  sleep 20; listed && break
  sleep 600
done
echo "$(date -u) | SUBMITTED $K v$V" >> $LOG
kaggle competitions submissions $C 2>&1 | sed -n 3p >> $LOG
