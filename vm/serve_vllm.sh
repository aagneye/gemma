#!/usr/bin/env bash
# Local scorer-equivalent vLLM server on the 4x T4 VM. Mirrors scripts/inference.py setup_vllm_server except:
# dtype fp16 (T4 has no bf16), lower memory target, max 8 sequences, CUDA graphs only for batch 1-8 (or eager),
# plus a local patch to vLLM's Triton attention tile size (T4 has 64 KB shared memory; see vm/README.md).
#   MODEL=gemma-4-31b-it-qat-w4a16-ct|gemma-4-12b-it-qat-w4a16-ct|gemma-4-e4b-it-qat-w4a16-ct [ADAPTER=<peft dir>]
#   [TP=4] [GPUS=1,2] [PORT=8000] [MODE=graphs|eager] [MEM=0.84] [ATTN=FLEX_ATTENTION] [MAXSEQ=8] bash serve_vllm.sh
# TP = tensor parallel size (the scorer uses 4 on 4xL4; the E4B fits one T4 with TP=1). GPUS = CUDA_VISIBLE_DEVICES,
# so several single-GPU servers can run side by side on different PORTs (one experiment per free T4).
# The 12B needs the Gemma4ForCausalLM override (as in the scorer); the 31B and E4B are served without overrides.
# LoRA is enabled only when ADAPTER is set.
source /mnt/biohub/kdata/gemma4/vllm-venv/bin/activate; cd /mnt/biohub/kdata/gemma4
export VLLM_NO_USAGE_STATS=1 VLLM_WORKER_MULTIPROC_METHOD=spawn VLLM_ENGINE_READY_TIMEOUT_S=1200 NCCL_P2P_DISABLE=1
MODEL=${MODEL:-gemma-4-12b-it-qat-w4a16-ct}
ADAPTER=${ADAPTER:-}
MODE=${MODE:-graphs}
TP=${TP:-4}
GPUS=${GPUS:-}
PORT=${PORT:-8000}
MAXSEQ=${MAXSEQ:-8}
ATTN=${ATTN:-}   # e.g. FLEX_ATTENTION; empty = vLLM default (Triton on T4)
case "$MODEL" in *e4b*|*e2b*) MEM=${MEM:-0.92};; *) MEM=${MEM:-0.84};; esac   # the E4B's 11.5 GB of weights need the headroom
[ -n "$GPUS" ] && export CUDA_VISIBLE_DEVICES=$GPUS
if [ "$MODE" = eager ]; then
  GRAPH_FLAGS=(--enforce-eager)
else
  GRAPH_FLAGS=(--compilation-config '{"cudagraph_capture_sizes": [1, 2, 4, 8]}')
fi
EXTRA=()
case "$MODEL" in *12b*) EXTRA+=(--hf-overrides '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}');; esac
[ -n "$ATTN" ] && EXTRA+=(--attention-backend "$ATTN")
[ -n "$ADAPTER" ] && EXTRA+=(--enable-lora --max-loras 1 --max-lora-rank 32 --lora-modules "main_lora=$ADAPTER")
echo "serve_vllm: model=$MODEL tp=$TP gpus=${GPUS:-all} port=$PORT mode=$MODE mem=$MEM maxseq=$MAXSEQ attn=${ATTN:-default} adapter=${ADAPTER:-none}"
vllm serve models/$MODEL --served-model-name $MODEL \
  --host 127.0.0.1 --port $PORT --tensor-parallel-size $TP --dtype float16 --max-model-len 32768 \
  --gpu-memory-utilization $MEM --max-num-seqs $MAXSEQ "${GRAPH_FLAGS[@]}" \
  --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
  --reasoning-config '{"reasoning_start_str": "<|channel>", "reasoning_end_str": "<channel|>"}' \
  "${EXTRA[@]}"
