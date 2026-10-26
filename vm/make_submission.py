#!/usr/bin/env python3
"""Build a competition submission directory + submission.zip for the Gemma 4 Developer Agent competition.

Preferred (2026-10-25): start from a validated bundle and add an adapter / switch the model:
  python make_submission.py --bundle submissions/v5_single --model gemma-4-e4b-it-qat-w4a16-ct \
         --adapter runs/e4b_smoke/final --out submissions/e4b_v5_smoke
Legacy: write a single-agent bundle from a prompt file and budgets (defaults = the shipped v5 profile):
  python make_submission.py --out submissions/base_e4b --model gemma-4-e4b-it-qat-w4a16-ct [--prompt prompts/system_v5.md]
Then validate inside harness-venv:  python make_submission.py --validate submissions/e4b_v5_smoke

Adapter packaging (G0 checks, all enforced): adapter_config.json gets `target_modules` as a plain list (vLLM splits
entries on "." and would reject the training regex), `base_model_name_or_path` = google/<declared model>,
inference_mode true; weights are cast to fp16 (halves the file) and must be finite; every LoRA key must start with
--check-prefix (default `base_model.model.model.language_model.layers.`, the key layout the scorer's vLLM maps);
the adapter must stay under --max-adapter-mib (3072, the organiser's size limit).
"""
import argparse, json, os, re, shutil, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = "gemma-4-31b-it-qat-w4a16-ct"          # overridable with --model (31b/12b/e4b/e2b QAT variants only)
EVAL = {"timeout_seconds": 90, "max_tool_calls": 28, "max_time_minutes": 8.0, "max_turns": 80}   # == v5 bundle
SAMPLING = {"temperature": 0.2, "top_p": 0.95, "max_output_tokens": 8192,
            "thinking_config": {"thinking_budget": 4096, "include_thoughts": True}}
TOOLS = ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def check_prompt(prompt):
    for bad in re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", prompt):
        if bad not in ("problem_description", "hints"): raise SystemExit(f"prompt contains ADK placeholder {{{bad}}} -> KeyError at runtime")


def write_bundle(out: Path, model: str, prompt: str, adapter: bool, skills_dir: Path | None = None):
    (out / "prompts").mkdir(parents=True, exist_ok=True); (out / "configs").mkdir(exist_ok=True)
    check_prompt(prompt)
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
        f"name: swe_agent\nmodel: {model}\n{adapter_line}instruction: !include prompts/system.md\ntools:\n{yaml_tools}\n{skills_yaml}"
        "generate_content_config: !include configs/sampling.yaml\n", encoding="utf-8")
    s = SAMPLING; tc = s["thinking_config"]
    (out / "configs" / "sampling.yaml").write_text(
        f"temperature: {s['temperature']}\ntop_p: {s['top_p']}\nmax_output_tokens: {s['max_output_tokens']}\n"
        f"thinking_config:\n  thinking_budget: {tc['thinking_budget']}\n  include_thoughts: true\n", encoding="utf-8")
    (out / "eval_config.yaml").write_text("evaluation:\n" + "".join(f"  {k}: {v}\n" for k, v in EVAL.items()), encoding="utf-8")


def copy_bundle(src: Path, out: Path, model: str | None, adapter: bool):
    """Copy a validated bundle; optionally override `model:` and add `adapter: main_lora` in every agent yaml."""
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("adapters", "*.zip", "__pycache__"))
    declared = None
    for y in sorted(out.rglob("*.yaml")) + sorted(out.rglob("*.yml")):
        text = y.read_text(encoding="utf-8")
        if not re.search(r"^model:\s*\S+", text, re.M): continue
        if model: text = re.sub(r"^model:\s*\S+", f"model: {model}", text, flags=re.M)
        declared = re.search(r"^model:\s*(\S+)", text, re.M).group(1)
        text = re.sub(r"^adapter:.*\n", "", text, flags=re.M)
        if adapter: text = re.sub(r"^(model:.*\n)", r"\1adapter: main_lora\n", text, count=1, flags=re.M)
        y.write_text(text, encoding="utf-8")
    assert declared, f"no `model:` line found in {src}"
    return declared


def package_adapter(adapter: Path, out: Path, model: str, check_prefix: str, max_mib: float):
    dst = out / "adapters" / "main_lora"; dst.mkdir(parents=True)
    cfg = json.load(open(adapter / "adapter_config.json"))
    # vLLM's LoRA loader validates peft_helper.target_modules by splitting entries on "." and checking the last
    # part against its supported module names -> a regex string (what training wrote) would be rejected.
    cfg["target_modules"] = LORA_TARGETS
    cfg["base_model_name_or_path"] = f"google/{model}"
    cfg["inference_mode"] = True
    json.dump(cfg, open(dst / "adapter_config.json", "w"), indent=2)
    import torch
    from safetensors.torch import load_file, save_file
    w = load_file(str(adapter / "adapter_model.safetensors"))
    keys = sorted(w)
    bad_prefix = [k for k in keys if not k.startswith(check_prefix)]
    assert not bad_prefix, f"G0 FAIL: {len(bad_prefix)} keys do not start with {check_prefix}: {bad_prefix[:3]}"
    names = {k.split(".lora_")[0].rsplit(".", 1)[-1] for k in keys}
    assert names <= set(LORA_TARGETS), f"G0 FAIL: unexpected LoRA module names {names - set(LORA_TARGETS)}"
    w = {k: v.to(torch.float16).contiguous() for k, v in w.items()}
    bad = [k for k, v in w.items() if not torch.isfinite(v).all()]
    assert not bad, f"G0 FAIL: non-finite after fp16 cast: {bad[:3]}"
    save_file(w, str(dst / "adapter_model.safetensors"), metadata={"format": "pt"})
    mb = os.path.getsize(dst / "adapter_model.safetensors") / 2**20
    assert mb <= max_mib, f"G0 FAIL: adapter {mb:.0f} MiB > {max_mib} MiB"
    layers = sorted({int(m.group(1)) for k in keys if (m := re.search(r"\.layers\.(\d+)\.", k))})
    print(f"G0 OK: adapter r={cfg.get('r')} alpha={cfg.get('lora_alpha')} targets={cfg['target_modules']} base={cfg['base_model_name_or_path']} | "
          f"{len(keys)} tensors, modules {sorted(names)}, layers {layers[0]}-{layers[-1]} ({len(layers)}), fp16 {mb:.0f} MiB, prefix {check_prefix}")
    return {"tensors": len(keys), "mib": round(mb, 1), "layers": len(layers), "modules": sorted(names), "r": cfg.get("r"), "alpha": cfg.get("lora_alpha")}


def zip_dir(out: Path):
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
    print("VALID. declared models:", sorted(models), "| adapters:", {k: getattr(v, "rank", None) for k, v in (getattr(ad, "adapters", {}) or {}).items()}, f"| size {total/2**20:.1f} MiB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out"); ap.add_argument("--adapter"); ap.add_argument("--validate"); ap.add_argument("--bundle", help="validated bundle dir to copy (preferred)")
    ap.add_argument("--model", default=None, help="declared model (default: the bundle's, or gemma-4-31b-it-qat-w4a16-ct)")
    ap.add_argument("--time", type=float, default=EVAL["max_time_minutes"]); ap.add_argument("--calls", type=int, default=EVAL["max_tool_calls"])
    ap.add_argument("--turns", type=int, default=EVAL["max_turns"]); ap.add_argument("--timeout", type=int, default=EVAL["timeout_seconds"])
    ap.add_argument("--prompt", default=str(HERE / "prompts" / "system_v5.md"), help="system prompt file (legacy path only)")
    ap.add_argument("--skills", help="directory with skill folders (each with SKILL.md) to ship under skills/ (legacy path only)")
    ap.add_argument("--thinking", type=int, default=SAMPLING["thinking_config"]["thinking_budget"]); ap.add_argument("--temperature", type=float, default=SAMPLING["temperature"])
    ap.add_argument("--check-prefix", default="base_model.model.model.language_model.layers."); ap.add_argument("--max-adapter-mib", type=float, default=3072)
    a = ap.parse_args()
    if a.validate:
        validate(Path(a.validate)); sys.exit(0)
    out = Path(a.out)
    if out.exists(): shutil.rmtree(out)
    if a.bundle:
        model = copy_bundle(Path(a.bundle), out, a.model, adapter=bool(a.adapter))
    else:
        model = a.model or MODEL
        EVAL.update(max_time_minutes=a.time, max_tool_calls=a.calls, max_turns=a.turns, timeout_seconds=a.timeout)
        SAMPLING["thinking_config"]["thinking_budget"] = a.thinking; SAMPLING["temperature"] = a.temperature
        write_bundle(out, model, Path(a.prompt).read_text(encoding="utf-8").strip(), adapter=bool(a.adapter), skills_dir=Path(a.skills) if a.skills else None)
    info = package_adapter(Path(a.adapter), out, model, a.check_prefix, a.max_adapter_mib) if a.adapter else None
    zip_dir(out)
    json.dump({"bundle": a.bundle, "model": model, "adapter": a.adapter, "g0": info}, open(out.with_suffix(".build.json"), "w"), indent=1)
