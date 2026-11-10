#!/usr/bin/env bash
# Replicate the Kaggle scorer HOST Python (the subprocess sandbox inherits its site-packages via _host_env.pth):
# python 3.12.13 + Kaggle image `pip freeze` (scratch/kfreeze/freeze.txt from the gemma4-scorer-env-freeze notebook)
# minus GPU frameworks, plus the competition wheelhouse (harness packages). Result: $R/$TARGET (default scorer-host-venv).
# EXTRA=<file> then adds those packages one by one, constrained to the versions already installed, so the Kaggle freeze
# stays as it is (TRAIN-pool venv for SWE-rebench tasks that need test packages the image lacks; never for EVAL):
#   TARGET=scorer-host-venv-plus EXTRA=~/gemma4_vm/extra_test_packages.txt bash build_scorer_host.sh
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; export PATH=$HOME/.local/bin:$PATH
TARGET=${TARGET:-scorer-host-venv}; EXTRA=${EXTRA:-}
SKIP='^(torch|torchvision|torchaudio|torchao|nvidia-|tensorflow|tf-|tf_|keras|jax|jaxlib|flax|optax|vllm|triton|xformers|flashinfer|cupy|cuda-|cudf|cuml|rapids|dask-cuda|pylibraft|rmm|ucx|bitsandbytes|deepspeed|apex|tensorrt|onnxruntime-gpu|mxnet|paddle|catboost|lightgbm|xgboost|opencv|thinc|spacy|en-core)'
grep -v '@ file://' scratch/kfreeze/freeze.txt | grep -viE "$SKIP" | grep -v '^-e ' > scratch/kfreeze/host_reqs.txt
wc -l scratch/kfreeze/host_reqs.txt
rm -rf $TARGET
uv venv --python 3.12.13 $TARGET
# install one by one tolerantly in a single resolver pass; --no-deps keeps exact Kaggle versions
uv pip install --python $TARGET/bin/python --no-deps -r scratch/kfreeze/host_reqs.txt 2>&1 | tail -5 || true
# anything that failed as a batch: retry individually so one bad pin does not drop the rest
$TARGET/bin/python -c "import pytest" 2>/dev/null || while read -r l; do uv pip install --python $TARGET/bin/python --no-deps "$l" >/dev/null 2>&1 || echo "SKIP $l"; done < scratch/kfreeze/host_reqs.txt
# harness packages exactly as Kaggle installs them (wheelhouse, no GPU wheels)
mkdir -p scratch/wh_host && rm -f scratch/wh_host/*
for w in data/wheelhouse/*.whl; do b=$(basename $w); case "$(echo $b | tr A-Z a-z)" in vllm*|torch*|flashinfer*|xformers*|triton*|nvidia*|*cutlass*) continue;; esac
  n=$b; case "$b" in *cu128*) case "$b" in *+cu128*) ;; *) n=${b/cu128/+cu128};; esac;; esac; ln -sf $R/$w scratch/wh_host/$n; done
uv pip install --python $TARGET/bin/python --no-deps --reinstall scratch/wh_host/*.whl 2>&1 | tail -3
$TARGET/bin/python -c "import pytest, swegemma, adk_submission, google.adk; print('pytest', pytest.__version__, 'ok')"
if [ -n "$EXTRA" ]; then
  uv pip freeze --python $TARGET/bin/python | grep -v "^-e " > scratch/kfreeze/${TARGET}_pins.txt
  grep -v "^#" $EXTRA | grep -v "^[[:space:]]*$" | while read -r p; do
    uv pip install --python $TARGET/bin/python -c scratch/kfreeze/${TARGET}_pins.txt "$p" >/dev/null 2>&1 && echo "EXTRA $p" || echo "SKIP extra $p"
  done
fi
echo HOST_DONE
