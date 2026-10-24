#!/usr/bin/env bash
# Push prepared Kaggle notebooks at a given UTC time (e.g. right after the weekly GPU quota reset).
#   bash push_at.sh "2026-10-24 00:05" dir1 [dir2 ...]
T=$1; shift; R=/mnt/biohub/kdata/gemma4; cd $R; source .venv/bin/activate
t=$(date -u -d "$T" +%s); while [ "$(date -u +%s)" -lt "$t" ]; do sleep 60; done
for d in "$@"; do echo "$(date -u) push $d: $(kaggle kernels push -p $d 2>&1 | tail -1)" >> logs/push_at.log; sleep 30; done
