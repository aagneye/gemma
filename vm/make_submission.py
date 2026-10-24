#!/usr/bin/env python3
"""Build a competition submission directory + submission.zip for the Gemma 4 Developer Agent competition.

Shipped agent = ONE root LlmAgent, the 6 core tools only (no graph tools, no sub-agent), system prompt and budgets
identical to what the training data advertised (vm/prepare_data.py: SYSTEM_PROMPT, BUDGET), thinking ON.

  python make_submission.py --out submissions/base_12b                       # prompt-only baseline (no adapter)
  python make_submission.py --out submissions/lora_v3_100 --adapter runs/12b_r32_v3/ckpt_100
Then validate inside harness-venv:  python make_submission.py --validate submissions/lora_v3_100
"""
import argparse, json, os, re, shutil, sys, zipfile
from pathlib import Path

MODEL = "gemma-4-12b-it-qat-w4a16-ct"          # overridable with --model (31b/12b/e4b/e2b QAT variants only)
EVAL = {"timeout_seconds": 150, "max_tool_calls": 50, "max_time_minutes": 5.0, "max_turns": 80}   # == prepare_data.BUDGET + prompt text
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "max_output_tokens": 8192,
            "thinking_config": {"thinking_budget": 4096, "include_thoughts": True}}
TOOLS = ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]


def system_prompt():
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    import prepare_data as P          # single source of truth for the trained system prompt
    sp = P.SYSTEM_PROMPT
    assert "{" not in sp and "}" not in sp, "ADK treats {x} in instructions as state variables"
    return sp


def build(out: Path, adapter: Path | None, prompt_file: Path | None = None, skills_dir: Path | None = None):
    if out.exists(): shutil.rmtree(out)
    (out / "prompts").mkdir(parents=True); (out / "configs").mkdir()
    prompt = prompt_file.read_text(encoding="utf-8").strip() if prompt_file else system_prompt()
    assert "{" not in prompt.replace("{\"", "").replace("\"}", "") or True   # ADK {var} templating: see check below
    for bad in re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", prompt):
        if bad not in ("problem_description", "hints"): raise SystemExit(f"prompt contains ADK placeholder {{{bad}}} -> KeyError at runtime")
    (out / "prompts" / "system.md").write_text(prompt + "\n", encoding="utf-8")
    yaml_tools = "\n".join(f"  - {t}" for t in TOOLS)
    adapter_line = "adapter: main_lora\n" if adapter else ""
    skills_yaml = ""
    if skills_dir:
        names = sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file())
        for n in names:
            shutil.copytree(skills_dir / n, out / "skills" / n, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            fm = (out / "skills" / n / "SKILL.md").read_text(encoding="utf-8")
            assert fm.startswith("---") and f"name: {n}" in fm.split("---")[1], f"SKILL.md of {n} must declare name: {n}"
        skills_yaml = "skills:\n" + "".join(f"  - skills/{n}\n" for n in names)
    (out / "agent.yaml").write_text(
        f"name: swe_agent\nmodel: {MODEL}\n{adapter_line}instruction: !include prompts/system.md\ntools:\n{yaml_tools}\n{skills_yaml}"
        "generate_content_config: !include configs/sampling.yaml\n", encoding="utf-8")
    s = SAMPLING; tc = s["thinking_config"]
    (out / "configs" / "sampling.yaml").write_text(
        f"temperature: {s['temperature']}\ntop_p: {s['top_p']}\nmax_output_tokens: {s['max_output_tokens']}\n"
        f"thinking_config:\n  thinking_budget: {tc['thinking_budget']}\n  include_thoughts: true\n", encoding="utf-8")
    (out / "eval_config.yaml").write_text("evaluation:\n" + "".join(f"  {k}: {v}\n" for k, v in EVAL.items()), encoding="utf-8")
    if adapter:
        dst = out / "adapters" / "main_lora"; dst.mkdir(parents=True)
        shutil.copy(adapter / "adapter_config.json", dst / "adapter_config.json")
        # vLLM's LoRA loader validates peft_helper.target_modules by splitting entries on "." and checking the last
        # part against its supported module names -> a regex string (what training wrote) would be rejected.
        cfg = json.load(open(dst / "adapter_config.json"))
        cfg["target_modules"] = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        cfg["base_model_name_or_path"] = "google/gemma-4-12b-it-qat-w4a16-ct"
        cfg["inference_mode"] = True
        json.dump(cfg, open(dst / "adapter_config.json", "w"), indent=2)
        # fp32 -> fp16 halves the file (524 MiB -> 262 MiB) and matches the fp16 serving dtype path; keep fp32 if safetensors/torch are missing
        try:
            import torch
            from safetensors.torch import load_file, save_file
            w = load_file(str(adapter / "adapter_model.safetensors"))
            w = {k: v.to(torch.float16).contiguous() for k, v in w.items()}
            bad = [k for k, v in w.items() if not torch.isfinite(v).all()]
            assert not bad, f"non-finite after fp16 cast: {bad[:3]}"
            save_file(w, str(dst / "adapter_model.safetensors"), metadata={"format": "pt"})
        except ImportError:
            shutil.copy(adapter / "adapter_model.safetensors", dst / "adapter_model.safetensors")
        cfg = json.load(open(dst / "adapter_config.json"))
        print("adapter: r=%s alpha=%s targets=%s base=%s" % (cfg.get("r"), cfg.get("lora_alpha"), cfg.get("target_modules"), cfg.get("base_model_name_or_path")))
        mb = os.path.getsize(dst / "adapter_model.safetensors") / 2**20
        print(f"adapter_model.safetensors {mb:.0f} MiB")
    zpath = out.with_suffix(".zip")
    if zpath.exists(): zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file(): z.write(p, p.relative_to(out).as_posix())
    print(f"wrote {out} and {zpath} ({zpath.stat().st_size/2**20:.1f} MiB)")


def validate(d: Path):
    from adk_submission import validate_directory, discover_adapters
    from adk_submission.discovery import discover_declared_models
    from swegemma.config import build_submission_limits, ALLOWED_SUBMISSION_EXTENSIONS, MAX_SUBMISSION_SIZE_BYTES
    limits, _ = build_submission_limits()
    for dp, dn, fn in os.walk(d, followlinks=False):
        for n in (*dn, *fn): assert not (Path(dp) / n).is_symlink(), f"symlink {n}"
    validate_directory(d, limits=limits)
    models = discover_declared_models(d); assert len(models) == 1, models
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            assert p.suffix.lower() in ALLOWED_SUBMISSION_EXTENSIONS, f"disallowed extension {p}"; total += p.stat().st_size
    assert total <= MAX_SUBMISSION_SIZE_BYTES, total
    ad = discover_adapters(str(d))
    print("VALID. declared models:", sorted(models), "| adapters:", list(getattr(ad, "adapters", {}) or {}), f"| size {total/2**20:.1f} MiB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out"); ap.add_argument("--adapter"); ap.add_argument("--validate")
    ap.add_argument("--model", default=MODEL); ap.add_argument("--time", type=float, default=EVAL["max_time_minutes"])
    ap.add_argument("--calls", type=int, default=EVAL["max_tool_calls"]); ap.add_argument("--turns", type=int, default=EVAL["max_turns"])
    ap.add_argument("--prompt", help="system prompt file (default: the trained prompt from prepare_data.py)")
    ap.add_argument("--skills", help="directory with skill folders (each with SKILL.md) to ship under skills/")
    ap.add_argument("--thinking", type=int, default=SAMPLING["thinking_config"]["thinking_budget"])
    a = ap.parse_args()
    MODEL = a.model; EVAL.update(max_time_minutes=a.time, max_tool_calls=a.calls, max_turns=a.turns)
    SAMPLING["thinking_config"]["thinking_budget"] = a.thinking
    if a.validate: validate(Path(a.validate))
    else: build(Path(a.out), Path(a.adapter) if a.adapter else None, Path(a.prompt) if a.prompt else None, Path(a.skills) if a.skills else None)
