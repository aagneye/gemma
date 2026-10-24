# everything-claude-code (ECC) — vendored skills

Source: https://github.com/affaan-m/everything-claude-code (Affaan Mustafa), commit `90606c8315ee09cafc303515c5f33024db6b9882`, MIT license (see `LICENSE`).

Copied verbatim into `../../.claude/skills/` (project skills, markdown only — no hooks, no Node scripts):

| Skill | Why we use it |
|---|---|
| `loop-design-check` | audit the factory loop: machine-decidable goal, boundaries next to the done-criterion, independent judge, retry caps |
| `benchmark-optimization-loop` | baseline first, one hypothesis per variant, ledger, stop when the gain is within noise |
| `eval-harness` | capability vs regression evals, pass@k / pass^k vocabulary for our paired evals |
| `agent-introspection-debugging` | failure capture -> diagnosis table -> contained recovery; structure for trace post-mortems |

Not adopted: hook-based features (all need Node.js: gateguard, strategic-compact hook, continuous-learning-v2), and skills that
duplicate superpowers / claude-skills (verification-loop, santa-method, conventional-commit-review).
Ideas adapted (not copied) into the Gemma agent prompt `vm/prompts/system_v5.md`: reproduce-first, callers lookup, explicit
minimal-diff don't-list, restate-the-objective recovery (from gateguard, orch-fix-defect, build-error-resolver,
agent-introspection-debugging).
