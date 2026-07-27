# OpenClaw and Hermes integration verification

Date: 2026-07-27
Dudu item: #1138

## Installed skill locations

- OpenClaw managed skill: `~/.openclaw/skills/grok-image-generation`
- Hermes local skill: `~/.hermes/skills/grok-image-generation` (symlink to this repository)

Both installations expose the same `SKILL.md` and `scripts/grok_image.py` behavior.

## Loading and tool mapping

### OpenClaw

A fresh `openclaw agent --session-id ... --json` run reported:

- `AGENTS.md`, `TOOLS.md`, and `MEMORY.md` injected from `~/.openclaw/workspace` without truncation.
- `grok-image-generation` present in the model-visible skill catalog.
- Explicit Grok requests routed to `grok-image-generation`.
- Explicit Codex/OpenAI OAuth requests remained on `codex-image-generation`.
- Explicit OpenClaw native requests remained on `image_generate`.

The skill is installed with `openclaw skills install <repo> --as grok-image-generation --global`; `openclaw skills info grok-image-generation --json` reports it eligible and model-visible.

### Hermes

Source inspection and a fresh one-shot run confirmed:

- `hermes -z` loads rules, memory, tools, and skills like a normal turn.
- `AGENTS.md` is loaded from the command working directory (`~/.hermes`).
- Built-in memory reads `~/.hermes/memories/MEMORY.md`.
- Local skills are discovered under `~/.hermes/skills/`.
- The `skills` and `terminal` toolsets were already enabled, so no `config.yaml` toolset change was required.
- `hermes skills list` reported `grok-image-generation` as local and enabled; `.usage.json` recorded one use in the successful test.

## Fresh-session results

### OpenClaw

- Session: `c93bc7b8-7d18-48e0-981e-926d94567693`
- Route report: Grok → `grok-image-generation`; Codex → `codex-image-generation`; native → `image_generate`.
- Provider: `grok-build-oauth`
- Output: `openclaw-grok.jpg`
- Format: JPEG, 1024×1024
- Bytes: 178,139
- SHA-256: `febcefe8e7943f613c39b6b87e077bed41b6eb0379ac9e27090051f88dd51989`
- Visual check: one translucent teal glass sphere centered on a black background.

### Hermes

- Session: `20260727_111000_4fa352`
- Route report: Grok → `grok-image-generation`; Codex → `codex-image-generation`; native → `image_generate`.
- Provider: `grok-build-oauth`
- Output: `hermes-grok-2.jpg`
- Format: JPEG, 1024×1024
- Bytes: 193,246
- SHA-256: `bcf60f23986540a450e6003ea13ea10300bc4d34589453f443689a6315e1c850`
- Visual check: one gold metallic cube centered on a dark navy background.

The first Hermes probe correctly used the skill but repeated the requested `.png` path even though the wrapper returned `.jpg`. The integration rule was tightened to require parsing, verifying, and reporting the wrapper JSON's returned `output`; the fresh rerun above reported the exact existing JPEG path.

## Instruction commits

- OpenClaw workspace: `b44e0ae2`
- Hermes home: `8dff688`

Both commits contain only the Grok routing/tool/memory additions. Pre-existing unrelated working-tree changes were preserved and left unstaged.
