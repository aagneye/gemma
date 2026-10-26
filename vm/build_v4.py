#!/usr/bin/env python3
"""Build agent bundles (legacy v4/v5 bundles and spec-described phase bundles) and prove they compile.

Legacy bundles (research/ARCHITECTURE_V4.md): v4_single, v4_phased, v5_single (built when --only is omitted).
Spec bundles: a spec is a small dict (see SPECS below, or --spec <file.json>):
  model      served model name (gemma-4-31b-it-qat-w4a16-ct, gemma-4-e4b-it-qat-w4a16-ct, ...)
  eval       {timeout, calls, minutes, turns}  -> eval_config.yaml (defaults: 90 s, 28 calls, 8.0 min, 80 turns)
  sampling   {thinking, temperature, top_p, max_output_tokens} defaults for every phase (4096, 0.2, 0.95, 8192)
  wrapper    single | sequential | loop   (loop takes max_iterations; default 3)
  phases     list of {name, prompt, tools[, thinking, temperature, top_p, max_output_tokens, include_contents,
             description]}; prompt = file in vm/prompts/. A single wrapper takes exactly one phase.
Prompt files may contain @CALLS@, @MINUTES@ and @TURNS@ (replaced by the eval budgets) but never curly braces.

  python build_v4.py --out-root submissions                          # legacy v4_single, v4_phased, v5_single
  python build_v4.py --out-root submissions --only e4b_v5 e4b_e5     # named specs and/or legacy names
  python build_v4.py --out-root submissions --spec my_spec.json      # external spec (name = "name" or file stem)
  python build_v4.py --list | --selftest
Each bundle is then checked: harness validate_directory + compile_submission into a live ADK agent tree (stub tools,
stub model) and the tree is printed. Run inside harness-venv or scorer-host-venv.
"""
import argparse, json, shutil, tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
TOOLS_ALL = ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]
TOOLS_KNOWN = TOOLS_ALL + ["get_code_neighbors", "search_similar_code", "get_code_subgraph"]
MODEL_31B = "gemma-4-31b-it-qat-w4a16-ct"
MODEL_E4B = "gemma-4-e4b-it-qat-w4a16-ct"
EVAL_DEFAULTS = dict(timeout=90, calls=28, minutes=8.0, turns=80)
SAMPLING_DEFAULTS = dict(thinking=4096, temperature=0.2, top_p=0.95, max_output_tokens=8192)
SAMPLING_KEYS = tuple(SAMPLING_DEFAULTS)
SOLVER_TOOLS = ["run_command", "read_file", "edit_file", "write_file"]
VERIFIER_TOOLS = ["run_command", "read_file", "edit_file", "get_status", "submit_patch"]


def sampling(thinking, temperature=0.2, top_p=0.95, max_output_tokens=8192):
    return (f"temperature: {temperature}\ntop_p: {top_p}\nmax_output_tokens: {max_output_tokens}\nthinking_config:\n"
            f"  thinking_budget: {thinking}\n  include_thoughts: true\n")


def eval_cfg(timeout, calls=28, minutes=8.0, turns=80):
    return (f"evaluation:\n  timeout_seconds: {timeout}\n  max_tool_calls: {calls}\n  max_time_minutes: {float(minutes)}\n"
            f"  max_turns: {turns}\n")


def tools_yaml(tools, indent="  "):
    return "".join(f"{indent}- {t}\n" for t in tools)


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- legacy bundles
def build_single(out, a, prompt="system_v4.md"):
    write(out / "prompts/system.md", (HERE / "prompts" / prompt).read_text(encoding="utf-8"))
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


LEGACY = {"v4_single": build_single, "v4_phased": build_phased,
          "v5_single": lambda out, a: build_single(out, a, "system_v5.md")}


# ------------------------------------------------------------------------------------------------------- spec bundles
def phase(name, prompt, tools, **kw):
    return {"name": name, "prompt": prompt, "tools": list(tools), **kw}


def single_spec(prompt, thinking, model=MODEL_E4B, eval=None, tools=TOOLS_ALL, name="swe_agent"):
    return {"model": model, "eval": {"timeout": 90, **(eval or {})}, "sampling": {"thinking": thinking},
            "wrapper": "single", "phases": [phase(name, prompt, tools)]}


def loop_spec(model, thinking, eval, max_iterations=3, solver="phase_solver.md", verifier="phase_verifier.md"):
    return {"model": model, "eval": eval, "sampling": {"thinking": thinking}, "wrapper": "loop",
            "max_iterations": max_iterations, "root_name": "swe_loop",
            "description": "Solver edits and hands over CHANGED/REPRO/TEST; verifier reruns the repro and one targeted "
                           "test, fixes once, submits; the loop repeats on a FAILED report.",
            "phases": [phase("solver", solver, SOLVER_TOOLS,
                             description="Locates and edits the source; hands over CHANGED / REPRO / TEST; cannot submit."),
                       phase("verifier", verifier, VERIFIER_TOOLS,
                             description="Reruns the repro and one targeted test, fixes once, checks the diff, submits.")]}


E5_EVAL = {"timeout": 90, "calls": 60, "minutes": 20.0, "turns": 120}
SPECS = {
    # E4B track (research/PLAN_TO_WIN.md Track B; plan Workstream 3). Baseline = submissions/e4b_v3t2k (v3 prompt,
    # thinking 2048, 28 calls / 8 min / 80 turns, timeout 240) which is NOT rebuilt here (byte-identical to the Kaggle run).
    "e4b_v5": single_spec("system_v5_1.md", 2048),                             # control: v5.1 prompt on the E4B
    "e4b_e5": loop_spec(MODEL_E4B, 2048, E5_EVAL),                             # E5: budget use, loop(solver, verifier) x3
    "e4b_e6_t1024": single_spec("e4b_demo.md", 1024),                          # E6: short prompt + demo, thinking sweep
    "e4b_e6_t2048": single_spec("e4b_demo.md", 2048),
    "e4b_e6_t4096": single_spec("e4b_demo.md", 4096),
    "e4b_e6r_t2048": single_spec("e4b_short.md", 2048),                        # research session's short prompt (if present)
    "e4b_e5_e6": loop_spec(MODEL_E4B, 2048, E5_EVAL, solver="phase_solver.md"),  # placeholder for stacking later
    # 31B (Workstream 2, E1 verifier gate): sequential solver -> verifier within the 0.22 profile budgets.
    "e1_31b": {**loop_spec(MODEL_31B, 4096, {"timeout": 90}), "wrapper": "sequential", "root_name": "swe_pipeline"},
}
SPECS["e1_31b"].pop("max_iterations", None)
SPECS.pop("e4b_e5_e6")


def render_prompt(name, ev):
    p = HERE / "prompts" / name
    if not p.exists(): raise FileNotFoundError(f"prompt {p} missing")
    text = p.read_text(encoding="utf-8")
    return (text.replace("@CALLS@", str(ev["calls"])).replace("@MINUTES@", f"{float(ev['minutes']):g}")
            .replace("@TURNS@", str(ev["turns"])))


def phase_sampling(spec, ph):
    s = {**SAMPLING_DEFAULTS, **spec.get("sampling", {}), **{k: ph[k] for k in SAMPLING_KEYS if k in ph}}
    return sampling(s["thinking"], s["temperature"], s["top_p"], s["max_output_tokens"])


def validate_spec(spec):
    phases = spec.get("phases") or []
    wrapper = spec.get("wrapper") or ("single" if len(phases) == 1 else "sequential")
    assert wrapper in ("single", "sequential", "loop"), f"unknown wrapper {wrapper}"
    assert phases, "a spec needs at least one phase"
    assert wrapper != "single" or len(phases) == 1, "a single wrapper takes exactly one phase"
    names = [p["name"] for p in phases]
    assert len(set(names)) == len(names), f"duplicate phase names {names}"
    for p in phases:
        assert p["name"].isidentifier(), f"phase name {p['name']!r} must be an identifier (ADK agent name)"
        bad = [t for t in p["tools"] if t not in TOOLS_KNOWN]
        assert not bad, f"unknown tools {bad} in phase {p['name']}"
        assert p.get("include_contents", "default") in ("default", "none")
    if wrapper == "loop": assert int(spec.get("max_iterations", 3)) >= 1
    return wrapper


def build_spec(out, spec):
    wrapper = validate_spec(spec)
    ev = {**EVAL_DEFAULTS, **spec.get("eval", {})}
    model = spec["model"]
    write(out / "eval_config.yaml", eval_cfg(ev["timeout"], ev["calls"], ev["minutes"], ev["turns"]))
    phases = spec["phases"]
    if wrapper == "single":
        ph = phases[0]
        write(out / "prompts/system.md", render_prompt(ph["prompt"], ev))
        write(out / "configs/sampling.yaml", phase_sampling(spec, ph))
        body = f"name: {ph['name']}\n"
        if ph.get("description"): body += f"description: {json.dumps(ph['description'])}\n"
        body += f"model: {model}\ninstruction: !include prompts/system.md\n"
        if ph.get("include_contents", "default") != "default": body += f"include_contents: {ph['include_contents']}\n"
        body += "tools:\n" + tools_yaml(ph["tools"]) + "generate_content_config: !include configs/sampling.yaml\n"
        write(out / "agent.yaml", body)
        return
    for ph in phases:
        write(out / f"prompts/{ph['name']}.md", render_prompt(ph["prompt"], ev))
        write(out / f"configs/sampling_{ph['name']}.yaml", phase_sampling(spec, ph))
        body = f"name: {ph['name']}\n"
        if ph.get("description"): body += f"description: {json.dumps(ph['description'])}\n"
        body += f"model: {model}\ninstruction: !include ../prompts/{ph['name']}.md\n"
        if ph.get("include_contents", "default") != "default": body += f"include_contents: {ph['include_contents']}\n"
        body += "tools:\n" + tools_yaml(ph["tools"]) + f"generate_content_config: !include ../configs/sampling_{ph['name']}.yaml\n"
        write(out / f"sub_agents/{ph['name']}.yaml", body)
    cls = {"sequential": "SequentialAgent", "loop": "LoopAgent"}[wrapper]
    root = f"agent_class: {cls}\nname: {spec.get('root_name', 'swe_pipeline')}\n"
    if spec.get("description"): root += f"description: {json.dumps(spec['description'])}\n"
    if wrapper == "loop": root += f"max_iterations: {int(spec.get('max_iterations', 3))}\n"
    root += "sub_agents:\n" + "".join(f"  - config_path: sub_agents/{ph['name']}.yaml\n" for ph in phases)
    write(out / "agent.yaml", root)


# ------------------------------------------------------------------------------------------------------------ checks
def check(out, model):
    import adk_submission
    from adk_submission import ModelRegistry, ToolRegistry, compile_submission, validate_directory
    from swegemma.config import build_submission_limits
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".yaml"):
            assert "{" not in p.read_text() or p.suffix == ".yaml", f"curly brace in {p} would be read as an ADK state template"
            assert "@CALLS@" not in p.read_text() and "@MINUTES@" not in p.read_text(), f"unrendered budget token in {p}"
    limits, gen = build_submission_limits()
    validate_directory(out, limits=limits)
    tools = {}
    for t in TOOLS_KNOWN:
        f = (lambda name: (lambda **kw: {"status": "ok", "tool": name}))(t); f.__name__ = t; f.__doc__ = t; tools[t] = f
    mr = ModelRegistry()
    from google.adk.models.lite_llm import LiteLlm
    mr.register(model, LiteLlm(model=f"openai/{model}", api_base="http://127.0.0.1:1/v1"))
    agent = compile_submission(out, tools, mr, limits=limits, generation_constraints=gen)
    def show(ag, d=0):
        tl = [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in (getattr(ag, "tools", None) or [])]
        extra = f" max_iterations={ag.max_iterations}" if getattr(ag, "max_iterations", None) else ""
        print("  " * d + f"- {type(ag).__name__} {ag.name} tools={tl} instr_chars={len(getattr(ag, 'instruction', '') or '')}{extra}")
        for s in getattr(ag, "sub_agents", []) or []: show(s, d + 1)
    show(agent)


def selftest():
    """The spec path must reproduce the legacy v5_single bundle byte for byte."""
    a = SimpleNamespace(thinking=4096, timeout=90, model=MODEL_31B)
    spec = single_spec("system_v5.md", 4096, model=MODEL_31B)
    with tempfile.TemporaryDirectory() as td:
        x, y = Path(td) / "legacy", Path(td) / "spec"
        LEGACY["v5_single"](x, a); build_spec(y, spec)
        fx = {p.relative_to(x).as_posix(): p.read_bytes() for p in x.rglob("*") if p.is_file()}
        fy = {p.relative_to(y).as_posix(): p.read_bytes() for p in y.rglob("*") if p.is_file()}
        assert fx == fy, f"spec build differs from legacy v5_single: {sorted(set(fx) ^ set(fy)) or [k for k in fx if fx[k] != fy.get(k)]}"
        for name, sp in SPECS.items():
            if not (HERE / "prompts" / sp["phases"][0]["prompt"]).exists(): continue
            z = Path(td) / name; build_spec(z, sp)
            for p in z.rglob("*.md"): assert "{" not in p.read_text(encoding="utf-8"), f"curly brace in {p}"
    print("SELFTEST OK (spec == legacy v5_single; all named specs render without curly braces)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out-root", default="submissions")
    ap.add_argument("--thinking", type=int, default=4096); ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--model", default=MODEL_31B, help="model for the legacy bundles (specs carry their own)")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--only", nargs="*", default=None, help="bundle names: legacy (v4_single, v4_phased, v5_single) or spec names")
    ap.add_argument("--spec", nargs="*", default=[], help="external spec JSON files")
    ap.add_argument("--list", action="store_true"); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-check", action="store_true", help="build only (no harness validation/compile)")
    a = ap.parse_args()
    if a.list:
        for n in LEGACY: print(f"{n:16} legacy")
        for n, s in SPECS.items():
            print(f"{n:16} {s['model']} {s.get('wrapper')} x{s.get('max_iterations', '')} eval={ {**EVAL_DEFAULTS, **s.get('eval', {})} } "
                  f"phases={[(p['name'], p['prompt']) for p in s['phases']]} thinking={s.get('sampling', {}).get('thinking')}")
        return
    if a.selftest: selftest(); return
    todo = []
    names = a.only if a.only is not None else list(LEGACY)
    for n in names:
        if n in LEGACY: todo.append((n, lambda out, n=n: LEGACY[n](out, a), a.model))
        elif n in SPECS: todo.append((n, lambda out, n=n: build_spec(out, SPECS[n]), SPECS[n]["model"]))
        else: raise SystemExit(f"unknown bundle {n}; --list shows the names")
    for f in a.spec:
        sp = json.load(open(f)); n = sp.get("name") or Path(f).stem
        todo.append((n, lambda out, sp=sp: build_spec(out, sp), sp["model"]))
    for name, fn, model in todo:
        out = Path(a.out_root) / (name + a.suffix); shutil.rmtree(out, ignore_errors=True); fn(out)
        print(f"== {out}")
        if not a.no_check: check(out, model); print("VALID + COMPILED")


if __name__ == "__main__":
    main()
