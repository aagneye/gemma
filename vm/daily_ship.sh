#!/usr/bin/env bash
# Never lose a daily slot: each UTC day after 00:10, submit the bundle named in results/ship.txt unless today already
# has a submission. ship.txt = one line: "<owner/kernel-slug> <kernel-version> <message...>" (update it when a bundle
# wins a paired eval; the kernel's output must already be byte-checked against its package).
R=/mnt/biohub/kdata/gemma4; cd $R; source .venv/bin/activate; LOG=logs/daily_ship.log; C=gemma-4-developer-agent
while true; do
  today=$(date -u +%Y-%m-%d)
  if [ "$(date -u +%H%M)" -ge 0010 ] && ! kaggle competitions submissions $C 2>/dev/null | sed -n 3p | grep -q " $today "; then
    read -r K V M < results/ship.txt
    out=$(kaggle competitions submit $C -k "$K" -f submission.zip -v "$V" -m "$M (daily ship $today)" 2>&1 | grep -v Warning | tail -1)
    echo "$(date -u) | $K v$V | $out" >> $LOG
    sleep 60; kaggle competitions submissions $C 2>/dev/null | sed -n 3p >> $LOG
  fi
  sleep 1800
done
