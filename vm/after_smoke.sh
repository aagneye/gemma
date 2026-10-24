#!/usr/bin/env bash
# Hand the T4s from local scoring to training: wait until the skills package (v2_12b) has finished N smoke tasks,
# record whether the skills were actually invoked, stop scoring + vLLM, then launch the curated-subset retrain.
#   bash after_smoke.sh [N=4]
N=${1:-4}
R=/mnt/biohub/kdata/gemma4; cd $R
LOG=logs/after_smoke.log
count() { cat results/local/v2_12b/*/task_results.jsonl 2>/dev/null | wc -l; }
until [ "$(count)" -ge "$N" ]; do
  tmux has-session -t score_v2 2>/dev/null || break
  sleep 120
done
{
  echo "$(date -u) v2 smoke: $(count) tasks done, resolved $(cat results/local/v2_12b/*/task_results.jsonl 2>/dev/null | grep -c '"resolved": true')"
  echo "skill calls in traces: locate=$(grep -o 'locate.py' results/local/v2_12b/*/traces/*.json 2>/dev/null | wc -l) finalize=$(grep -o 'finalize.py' results/local/v2_12b/*/traces/*.json 2>/dev/null | wc -l) run_skill_script=$(grep -o 'run_skill_script' results/local/v2_12b/*/traces/*.json 2>/dev/null | wc -l)"
} >> $LOG
tmux kill-session -t score_v2 2>/dev/null
sleep 5
docker ps -q | xargs -r docker rm -f > /dev/null 2>&1
tmux kill-session -t vllm 2>/dev/null
sleep 20
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)" -lt 500 ]; do sleep 10; done
until [ -f datasets/sft_v4_mid/tok_12b_7k/train.parquet ]; do sleep 60; done
# 3-step DDP smoke test of the fixed trainer: must print SYNC_OK and exit cleanly before the long run starts
echo "$(date -u) GPUs free -> DDP smoke test" >> $LOG
source .venv/bin/activate
rm -rf runs/ddp_smoke
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 OMP_NUM_THREADS=8 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True timeout 3600 \
  torchrun --standalone --nproc_per_node 4 ~/gemma4_vm/train_qlora.py --model models/gemma-4-12B-it-qat-q4_0-unquantized \
  --data datasets/sft_v4_mid/tok_12b_7k --out runs/ddp_smoke --max-steps 3 --grad-accum 2 --rank 32 --lr 1e-4 \
  --max-len 7168 --chunk 512 --log-every 1 --save-every 1000 > logs/ddp_smoke.log 2>&1
deactivate
grep -E "SYNC_|saved ->|Traceback|Error" logs/ddp_smoke.log | tail -6 >> $LOG
if grep -q "SYNC_MISMATCH\|Traceback" logs/ddp_smoke.log || ! grep -q "SYNC_OK step 3" logs/ddp_smoke.log || ! grep -q "saved ->" logs/ddp_smoke.log; then
  echo "$(date -u) DDP SMOKE FAILED -> not launching the long run (see logs/ddp_smoke.log)" >> $LOG; exit 1
fi
echo "$(date -u) DDP smoke OK -> launching 12b_r32_v4mid" >> $LOG
bash ~/gemma4_vm/launch_train.sh 12b_r32_v4mid datasets/sft_v4_mid/tok_12b_7k 1 32 1e-4 4 "" >> $LOG 2>&1
