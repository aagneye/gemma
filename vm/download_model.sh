#!/usr/bin/env bash
# Download a Gemma 4 QAT checkpoint into models/<local_name> (ungated; resumable).
#   bash download_model.sh google/gemma-4-E4B-it-qat-w4a16-ct gemma-4-e4b-it-qat-w4a16-ct
R=/mnt/biohub/kdata/gemma4; cd $R; source .venv/bin/activate
python - "$1" "models/$2" <<'PY'
import sys
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], max_workers=8))
PY
echo DL_DONE
