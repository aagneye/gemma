#!/usr/bin/env bash
# Launch QLoRA training on the 4x T4 VM inside tmux so it survives SSH disconnects.
#   [GPUS=0,1,3 NPROC=3] bash launch_train.sh <run_name> <tokenized_dir> [epochs] [rank] [lr] [grad_accum]
# Example: bash launch_train.sh 12b_r32_v1 datasets/sft/tok_12b_8k 2 32 1e-4 4
set -euo pipefail
RUN=${1:?run name}; DATA=${2:?tokenized dir}; EPOCHS=${3:-2}; RANK=${4:-32}; LR=${5:-1e-4}; GA=${6:-4}; EXTRA=${7:-}
GPUS=${GPUS:-0,1,2,3}; NPROC=${NPROC:-4}   # the VM is shared with other projects: pass only the free GPUs
ROOT=/mnt/biohub/kdata/gemma4; cd "$ROOT"; mkdir -p runs logs
CMD="source $ROOT/.venv/bin/activate && cd $ROOT && NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 OMP_NUM_THREADS=8 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=$GPUS \
torchrun --standalone --nproc_per_node $NPROC ~/gemma4_vm/train_qlora.py \
  --model models/gemma-4-12B-it-qat-q4_0-unquantized --data $DATA --out runs/$RUN \
  --epochs $EPOCHS --rank $RANK --lr $LR --grad-accum $GA --max-len 7168 --chunk 512 --save-every 100 --log-every 5 $EXTRA \
  2>&1 | tee -a logs/$RUN.log"
tmux kill-session -t "train_$RUN" 2>/dev/null || true
tmux new-session -d -s "train_$RUN" "bash -lc '$CMD'"
echo "started tmux session train_$RUN; follow with: tail -f $ROOT/logs/$RUN.log"
