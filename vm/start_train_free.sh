#!/usr/bin/env bash
# The VM is shared with other projects: wait for free T4s, run a DDP smoke on them, then launch the long run.
#   bash start_train_free.sh [--model <path>] [--data <tokenized_dir>] [--run <name>] [--max-len N] [--epochs E] [--rank R]
#                            [--lr LR] [--alpha A] [--max-gpus N] [--extra "<args>"] [min_gpus=2]
# Effective batch is kept at ~16 sequences (grad_accum = round(16 / n_gpus)). GPU 0 belongs to another project
# (never free, never touched); --max-gpus caps how many free GPUs we take so a T4 stays free for E4B serving.
MODEL=models/gemma-4-12B-it-qat-q4_0-unquantized; DATA=datasets/sft_v4_mid/tok_12b_7k; RUN=12b_r32_v4mid; MAXLEN=7168
EPOCHS=1; RANK=32; LR=1e-4; ALPHA=""; MAXG=4; EXTRA=""
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --model) MODEL=$2; shift 2;; --data) DATA=$2; shift 2;; --run) RUN=$2; shift 2;; --max-len) MAXLEN=$2; shift 2;;
    --epochs) EPOCHS=$2; shift 2;; --rank) RANK=$2; shift 2;; --lr) LR=$2; shift 2;; --alpha) ALPHA=$2; shift 2;;
    --max-gpus) MAXG=$2; shift 2;; --extra) EXTRA=$2; shift 2;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
MIN=${1:-2}; R=/mnt/biohub/kdata/gemma4; cd $R; LOG=logs/start_train_free.log
[ -n "$ALPHA" ] && EXTRA="$EXTRA --alpha $ALPHA"
free_gpus() { nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2<500{print $1}' | head -n "$MAXG" | paste -sd, ; }
ngpu() { echo "$1" | tr ',' '\n' | grep -c . ; }
until G=$(free_gpus); [ "$(ngpu "$G")" -ge "$MIN" ]; do sleep 60; done
N=$(ngpu "$G"); GA=$(( (16 + N / 2) / N ))
echo "$(date -u) run $RUN model $MODEL data $DATA free GPUs $G (n=$N, grad_accum $GA) -> DDP smoke test" >> $LOG
source .venv/bin/activate
rm -rf runs/ddp_smoke_$RUN
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 OMP_NUM_THREADS=8 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=$G timeout 3600 \
  torchrun --standalone --nproc_per_node $N ~/gemma4_vm/train_qlora.py --model $MODEL \
  --data $DATA --out runs/ddp_smoke_$RUN --max-steps 3 --grad-accum 2 --rank $RANK --lr $LR \
  --max-len $MAXLEN --chunk 512 --log-every 1 --save-every 1000 $EXTRA > logs/ddp_smoke_$RUN.log 2>&1
deactivate
grep -E "SYNC_|saved ->|Traceback|Error" logs/ddp_smoke_$RUN.log | tail -6 >> $LOG
if grep -q "SYNC_MISMATCH\|Traceback" logs/ddp_smoke_$RUN.log || ! grep -q "SYNC_OK step 3" logs/ddp_smoke_$RUN.log || ! grep -q "saved ->" logs/ddp_smoke_$RUN.log; then
  echo "$(date -u) DDP SMOKE FAILED -> not launching $RUN (see logs/ddp_smoke_$RUN.log)" >> $LOG; exit 1
fi
echo "$(date -u) DDP smoke OK -> launching $RUN on GPUs $G" >> $LOG
GPUS=$G NPROC=$N MODEL=$MODEL MAXLEN=$MAXLEN bash ~/gemma4_vm/launch_train.sh $RUN $DATA $EPOCHS $RANK $LR $GA "$EXTRA" >> $LOG 2>&1
