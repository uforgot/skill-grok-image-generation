# Release readiness

Date: 2026-07-27
Status: ready for local OpenClaw and Hermes use

## Package

The final package contains:

- a portable [`SKILL.md`](../SKILL.md) with explicit provider routing;
- [`scripts/grok_image.py`](../scripts/grok_image.py) for deterministic generation and editing;
- 40 tests covering wrapper behavior, packaging, documentation, committed artifacts, and fail-closed paths;
- real generated and edited samples under [`examples/`](../examples/);
- OpenClaw and Hermes integration instructions and verification records.

No source file assumes a specific OpenClaw workspace or Hermes installation path. The skill resolves its wrapper relative to `SKILL.md`.

## Verified capabilities

- Real grok.com OAuth preflight
- Native Grok Build `image_gen`
- Native Grok Build `image_edit`
- `auto`, `1:1`, `16:9`, `9:16`, `4:3`, and `3:4` routing
- Provider-corrected output extension handling
- Session-bound result discovery
- Atomic copy and SHA-256 verification
- Edit source validation and overwrite protection
- OpenClaw managed-skill discovery
- Hermes local-skill discovery
- Discord-readable output files

## Verified fail-closed behavior

Fresh OpenClaw sessions and executable CLI tests covered:

- expired or missing grok.com OAuth;
- image-tool permission cancellation;
- timeout;
- moderation block.

Every case returned a cause, `fallback_used: false`, a next action, and a unified `user_message`. No case invoked OpenClaw `image_generate`, Codex image generation, the xAI REST API, or `XAI_API_KEY`.

## Installation targets

- OpenClaw: managed skill named `grok-image-generation`
- Hermes: local skill named `grok-image-generation`

The final verification confirmed that installed `SKILL.md` and wrapper hashes matched this repository.

## Validation commands

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/grok_image.py tests/*.py
openclaw skills info grok-image-generation --json
grok models
```

Expected state:

- 40 tests pass.
- Skill metadata reports eligible and model-visible in OpenClaw.
- `grok models` confirms the grok.com login.
- Repository documentation links resolve.

## Evidence

- Generate/edit results: [`e2e-1139-results.json`](../examples/e2e-1139-results.json)
- Fail-closed results: [`fail-closed-1140-results.json`](../examples/fail-closed-1140-results.json)
- OpenClaw/Hermes integration: [`integration-openclaw-hermes.md`](integration-openclaw-hermes.md)
- OpenClaw end-to-end review: [`openclaw-e2e-review.md`](openclaw-e2e-review.md)
- Error behavior: [`fail-closed-errors.md`](fail-closed-errors.md)

## Remaining limitations

- Edit V1 accepts one local source image.
- The Grok provider chooses exact output dimensions and format.
- Results remain nondeterministic and require visual review.
- Grok Build CLI output or session storage may change in future versions.
- Named real-person generation requires a real, consented reference through the edit flow.

## Final review

All Dudu items #1131–#1140 reached review with separate commits and verification evidence. The user approved finalization on 2026-07-27; after the final documentation commit and remote push, those items can move from review to done.
