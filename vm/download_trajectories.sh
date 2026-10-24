#!/usr/bin/env bash
# Pull licence-clean open SWE-agent trajectory corpora (CC BY 4.0 / MIT) for SFT.
set -euo pipefail
ROOT=/data/biohub/kdata/gemma4; cd "$ROOT"; source .venv/bin/activate
mkdir -p datasets
# Streamed/filtered in prepare_data.py; here we only snapshot the repos (resumable).
hf download nvidia/SWE-Hero-openhands-trajectories --repo-type dataset --local-dir datasets/swe-hero
hf download nvidia/Nemotron-SFT-SWE-v2 --repo-type dataset --local-dir datasets/nemotron-sft-swe-v2
hf download Kwai-Klear/SWE-smith-mini_swe_agent_plus-trajectories-66k --repo-type dataset --local-dir datasets/klear-66k
hf download nebius/SWE-rebench-openhands-trajectories --repo-type dataset --local-dir datasets/nebius-openhands
# Open-SWE-Traces is large (207k); fetch after the smaller ones work end-to-end:
# hf download nvidia/Open-SWE-Traces --repo-type dataset --local-dir datasets/open-swe-traces
du -sh datasets/*
