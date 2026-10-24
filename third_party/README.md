# third_party/ — vendored Claude Code skill repositories (shallow clones, 2026-10-17)

| Directory | Source | Commit | Claude Code plugin(s) |
|---|---|---|---|
| `superpowers/` | https://github.com/obra/superpowers.git | bb92a77741419a4ab5f06e711a283343f1ada0c3 | `superpowers@superpowers-dev` |
| `claude-skills/` | https://github.com/alirezarezvani/claude-skills.git | 19392f7a08264ed00486a251f5b2098321771f94 | `engineering-skills`, `engineering-advanced-skills`, `product-skills` (+ marketing, c-level, finance, ra-qm at user scope) `@claude-code-skills` |
| `ecc/` (skills copied into `.claude/skills/`) | https://github.com/affaan-m/everything-claude-code | 90606c8315ee09cafc303515c5f33024db6b9882 | none — 4 markdown skills vendored as project skills, see `ecc/README.md` |

These are local reference copies. Claude Code loads the skills through the plugin marketplaces declared in
`../.claude/settings.json` (same repos, same commits as the installed plugin cache). To update a copy:
`git -C third_party/<dir> pull`. Licenses: see each repo's LICENSE.

Not enabled on purpose: claude-skills sub-plugins that ship hooks (agent-memory, security-guidance, skillopt-sleep,
self-improving-agent, playwright-pro). Superpowers' own SessionStart hook is part of the superpowers plugin.
