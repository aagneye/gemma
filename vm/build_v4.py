#!/usr/bin/env python3
"""Build the architecture-v4 bundles (research/ARCHITECTURE_V4.md) and prove they compile.

  python build_v4.py --out-root submissions [--thinking 4096] [--timeout 90] [--model gemma-4-31b-it-qat-w4a16-ct]
Writes <out-root>/v4_single and <out-root>/v4_phased, then for each: harness validate_directory + compile_submission
into a live ADK agent tree (stub tools / stub model), printing the agent tree. Run inside harness-venv.
"""
import argparse, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_ALL = ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]


def sampling(thinking):
    return (f"temperature: 0.2\ntop_p: 0.95\nmax_output_tokens: 8192\nthinking_config:\n"
            f"  thinking_budget: {thinking}\n  include_thoughts: true\n")


def eval_cfg(timeout):
    return (f"evaluation:\n  timeout_seconds: {timeout}\n  max_tool_calls: 28\n  max_time_minutes: 8.0\n  max_turns: 80\n")


def tools_yaml(tools, indent="  "):
    return "".join(f"{indent}- {t}\n" for t in tools)


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")


def build_single(out, a):
    write(out / "prompts/system.md", (HERE / "prompts/system_v4.md").read_text(encoding="utf-8"))
    write(out / "configs/sampling.yaml", sampling(a.thinking))
    write(out / "eval_config.yaml", eval_cfg(a.timeout))
    write(out / "agent.yaml", f"name: swe_agent\nmodel: {a.model}\ninstruction: !include prompts/system.md\ntools:\n"
          + tools_yaml(TOOLS_ALL) + "generate_content_config: !include configs/sampling.yaml\n")


def build_phased(out, a):
    phases = [("scout", "Locates the exact code to change; read-only; hands over LOCATION/CHANGE/OLD CODE.",
               ["run_command", "read_file"]),
              ("fixer", "Applies the change the scout located, including parallel implementations.",
               ["read_file", "edit_file", "write_file", "run_command"]),
              ("finisher", "Runs one targeted test, fixes once if needed, checks the diff and submits the patch.",
               ["run_command", "read_file", "edit_file", "get_status", "submit_patch"])]
    write(out / "configs/sampling.yaml", sampling(a.thinking))
    write(out / "eval_config.yaml", eval_cfg(a.timeout))
    for name, desc, tools in phases:
        write(out / f"prompts/{name}.md", (HERE / f"prompts/v4_{name}.md").read_text(encoding="utf-8"))
        write(out / f"sub_agents/{name}.yaml",
              f"name: {name}\ndescription: {desc}\nmodel: {a.model}\ninstruction: !include ../prompts/{name}.md\n"
              f"tools:\n{tools_yaml(tools)}generate_content_config: !include ../configs/sampling.yaml\n")
    write(out / "agent.yaml",
          "agent_class: SequentialAgent\nname: swe_pipeline\n"
          "description: Scout locates, fixer edits, finisher tests and submits; one shared history and budget.\n"
          "sub_agents:\n" + "".join(f"  - config_path: sub_agents/{n}.yaml\n" for n, _, _ in phases))


def check(out, model):
    import adk_submission
    from adk_submission import ModelRegistry, ToolRegistry, compile_submission, validate_directory
    from swegemma.config import build_submission_limits
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".yaml"):
            assert "{" not in p.read_text() or p.suffix == ".yaml", f"curly brace in {p} would be read as an ADK state template"
    limits, gen = build_submission_limits()
    validate_directory(out, limits=limits)
    def stub(**kw): return {"status": "ok"}
    tools = {}
    for t in TOOLS_ALL + ["get_code_neighbors", "search_similar_code", "get_code_subgraph"]:
        f = (lambda name: (lambda **kw: {"status": "ok", "tool": name}))(t); f.__name__ = t; f.__doc__ = t; tools[t] = f
    mr = ModelRegistry()
    from google.adk.models.lite_llm import LiteLlm
    mr.register(model, LiteLlm(model=f"openai/{model}", api_base="http://127.0.0.1:1/v1"))
    agent = compile_submission(out, tools, mr, limits=limits, generation_constraints=gen)
    def show(ag, d=0):
        tl = [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in (getattr(ag, "tools", None) or [])]
        print("  " * d + f"- {type(ag).__name__} {ag.name} tools={tl} instr_chars={len(getattr(ag, 'instruction', '') or '')}")
        for s in getattr(ag, "sub_agents", []) or []: show(s, d + 1)
    show(agent)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out-root", default="submissions")
    ap.add_argument("--thinking", type=int, default=4096); ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--model", default="gemma-4-31b-it-qat-w4a16-ct"); ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    for name, fn in (("v4_single", build_single), ("v4_phased", build_phased)):
        out = Path(a.out_root) / (name + a.suffix); shutil.rmtree(out, ignore_errors=True); fn(out, a)
        print(f"== {out}"); check(out, a.model); print("VALID + COMPILED")


if __name__ == "__main__":
    main()
