#!/usr/bin/env bash
# The VM is shared with other projects: run the DDP smoke + the 12b_r32_v4mid retrain on whichever T4s are free.
#   bash start_train_free.sh [min_gpus=3]
# Effective batch is kept at ~16 sequences (grad_accum = round(16 / n_gpus)).
MIN=${1:-3}; R=/mnt/biohub/kdata/gemma4; cd $R; LOG=logs/after_smoke.log
free_gpus() { nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2<500{print $1}' | paste -sd, ; }
ngpu() { echo "$1" | tr ',' '\n' | grep -c . ; }
until G=$(free_gpus); [ "$(ngpu "$G")" -ge "$MIN" ]; do sleep 60; done
N=$(ngpu "$G"); GA=$(( (16 + N / 2) / N ))
echo "$(date -u) free GPUs $G (n=$N, grad_accum $GA) -> DDP smoke test" >> $LOG
source .venv/bin/activate
rm -rf runs/ddp_smoke
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 OMP_NUM_THREADS=8 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=$G timeout 3600 \
  torchrun --standalone --nproc_per_node $N ~/gemma4_vm/train_qlora.py --model models/gemma-4-12B-it-qat-q4_0-unquantized \
  --data datasets/sft_v4_mid/tok_12b_7k --out runs/ddp_smoke --max-steps 3 --grad-accum 2 --rank 32 --lr 1e-4 \
  --max-len 7168 --chunk 512 --log-every 1 --save-every 1000 > logs/ddp_smoke.log 2>&1
deactivate
grep -E "SYNC_|saved ->|Traceback|Error" logs/ddp_smoke.log | tail -6 >> $LOG
if grep -q "SYNC_MISMATCH\|Traceback" logs/ddp_smoke.log || ! grep -q "SYNC_OK step 3" logs/ddp_smoke.log || ! grep -q "saved ->" logs/ddp_smoke.log; then
  echo "$(date -u) DDP SMOKE FAILED -> not launching the long run (see logs/ddp_smoke.log)" >> $LOG; exit 1
fi
echo "$(date -u) DDP smoke OK -> launching 12b_r32_v4mid on GPUs $G" >> $LOG
GPUS=$G NPROC=$N bash ~/gemma4_vm/launch_train.sh 12b_r32_v4mid datasets/sft_v4_mid/tok_12b_7k 1 32 1e-4 $GA "" >> $LOG 2>&1
