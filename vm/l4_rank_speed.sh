#!/usr/bin/env bash
# Kaggle side of the round-2 speed test (Nov 19, plan step 1; user approval Nov 19: one speed check on 4xL4, no agent
# runs). One speed-only run of l4_speed_check.sh per rank, with the rank-sliced speed bundles (vm/slice_adapter.py ->
# submissions/budgetfit_v5_spd<rank>). About 20 minutes of 4xL4 per rank.
#   bash l4_rank_speed.sh ["16 8"]      -> results/speed/l4_r<rank>.txt
set -u
cd /mnt/biohub/kdata/gemma4
for r in ${1:-16 8}; do
  SPEED_ONLY=1 DS=aagneye/gemma4-31b-lora-r$r-speed NB=aagneye/gemma4-31b-lora-speed-r$r TITLE="Gemma4 31B LoRA speed r$r" \
    OUTF=results/speed/l4_r$r.txt S=tmp/speedcheck_r$r MAX_SLOW=${MAX_SLOW:-1.10} TOK=1 \
    bash ~/gemma4_vm/l4_speed_check.sh none submissions/budgetfit_v5_spd$r
done
echo "$(date -u) l4_rank_speed done"
