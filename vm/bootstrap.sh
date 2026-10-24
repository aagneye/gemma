#!/usr/bin/env bash
# Bootstrap the Azure VM (Standard_NC64as_T4_v3: 4x Tesla T4 16 GB, sm75, fp16 only) for the
# Gemma 4 Developer Agent competition. Idempotent. Run as azureuser:
#   bash bootstrap.sh
set -euo pipefail
ROOT=/data/biohub/kdata/gemma4
mkdir -p "$ROOT"/{data,models,datasets,runs,logs,scripts}
cd "$ROOT"

echo "== system =="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
df -h /data | tail -1
nproc; free -g | head -2

echo "== apt deps =="
sudo apt-get update -qq
sudo apt-get install -y -qq git git-lfs build-essential tmux htop jq unzip pigz aria2 >/dev/null
command -v docker >/dev/null || { curl -fsSL https://get.docker.com | sudo sh; sudo usermod -aG docker "$USER"; }
git lfs install --skip-repo

echo "== uv + python 3.12 venv =="
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
export PATH="$HOME/.local/bin:$PATH"
[ -d "$ROOT/.venv" ] || uv venv --python 3.12 "$ROOT/.venv"
source "$ROOT/.venv/bin/activate"

echo "== python packages (CUDA 12.4 wheels; T4 = sm75) =="
uv pip install --upgrade pip
uv pip install "torch==2.6.*" --index-url https://download.pytorch.org/whl/cu124
uv pip install "transformers>=5.5" "peft>=0.19.1" "trl>=0.21" "datasets" "accelerate" "bitsandbytes>=0.45" \
  "huggingface_hub[cli]" "kaggle" "safetensors" "sentencepiece" "numpy" "networkx" "rank-bm25" "tqdm" "pyyaml" "orjson"
# Unsloth: T4-compatible (fp16). If the pin fails, fall back to plain PEFT path in train_qlora.py (--no-unsloth).
uv pip install "unsloth" "unsloth_zoo" || echo "WARN: unsloth install failed; train_qlora.py --no-unsloth still works"
python - <<'PY'
import torch, transformers, peft
print("torch", torch.__version__, "cuda", torch.version.cuda, "gpus", torch.cuda.device_count(),
      "bf16", torch.cuda.is_bf16_supported())
print("transformers", transformers.__version__, "peft", peft.__version__)
PY

echo "== credentials check =="
[ -f ~/.kaggle/kaggle.json ] && echo "kaggle.json present" || echo "MISSING ~/.kaggle/kaggle.json (create from kaggle.com/settings -> API token; chmod 600)"
[ -n "${HF_TOKEN:-}" ] || [ -f ~/.cache/huggingface/token ] && echo "HF token present" || echo "MISSING HF token: run 'huggingface-cli login' (accept the Gemma 4 licence on HF first)"
echo "bootstrap done -> $ROOT (activate with: source $ROOT/.venv/bin/activate)"
