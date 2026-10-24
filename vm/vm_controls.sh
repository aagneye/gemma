#!/usr/bin/env bash
# Gold/empty soundness controls on the VM with the subprocess sandbox (the sandbox Kaggle's notebook uses).
# Output: results/vm_sub_gold.csv, results/vm_sub_empty.csv; logs/vmctl_*.log
R=/mnt/biohub/kdata/gemma4; cd $R; source ${HOSTVENV:-scorer-host-venv}/bin/activate
for m in gold empty; do
  python ~/gemma4_vm/gold_check.py --root data/comp --stub data/comp/sample_submission --sandbox subprocess --mode $m \
    --concurrency 12 --verification-timeout 300 --out results/vm_sub_$m.csv > logs/vmctl_$m.log 2>&1
done
echo VMCTL_DONE >> logs/vmctl_empty.log
