# Grok Image Skill

Generate and edit images with Grok Build’s native `image_gen` and `image_edit` tools through an existing grok.com OAuth session.

This package is built for OpenClaw and Hermes. It does **not** call the xAI REST API, does not pass `XAI_API_KEY`, and never changes providers automatically after a Grok failure.

**Status:** verified for local use on 2026-07-27 with real OpenClaw and Hermes sessions, generation and editing samples, and fail-closed tests.

## What it does

- Generates images with Grok Build native `image_gen`.
- Edits one local JPEG, PNG, or WebP with native `image_edit`.
- Supports `auto`, `1:1`, `16:9`, `9:16`, `4:3`, and `3:4`.
- Restricts each Grok run to one requested image tool and disables web search.
- Uses non-interactive approval for headless agent runs.
- Resolves results from the current Grok session instead of selecting the newest global file.
- Copies atomically, preserves the provider’s real extension, and verifies SHA-256.
- Stops on OAuth, permission, timeout, moderation, provider, or output errors without fallback.

## Requirements

- Python 3.9+
- Grok Build CLI on `PATH`
- `grok models` reports `You are logged in with grok.com.`
- A writable output directory
- For edits, one readable local JPEG, PNG, or WebP source

## Install

### OpenClaw

Install directly from GitHub as a managed skill:

```bash
openclaw skills install \
  git:https://github.com/uforgot/skill-grok-image-generation.git \
  --as grok-image-generation \
  --global
```

Update an existing installation with `--force`, then verify discovery:

```bash
openclaw skills info grok-image-generation --json
```

The result should report `eligible: true` and `modelVisible: true`.

### Hermes

Clone the repository and expose it as a local skill directory:

```bash
git clone \
  https://github.com/uforgot/skill-grok-image-generation.git \
  /path/to/skill-grok-image-generation

ln -sfn \
  /path/to/skill-grok-image-generation \
  ~/.hermes/skills/grok-image-generation

hermes skills list
```

Hermes must have its skills and terminal toolsets enabled.

## Agent routing

[`SKILL.md`](SKILL.md) is the canonical agent workflow.

- Explicit Grok, Grok Imagine, grok.com OAuth, or Grok Build request → this skill.
- Explicit Codex or OpenAI OAuth image request → existing Codex image skill.
- Explicit OpenClaw or Hermes native image request → that runtime’s native image tool.
- No provider preference → preserve the runtime’s existing default.
- Grok failure → stop and report the Grok error; never choose another provider automatically.

## Quick start

### Generate

```bash
python3 scripts/grok_image.py generate \
  "A paper-cut forest at dawn, soft layered shadows, no text" \
  --aspect-ratio 16:9 \
  --output ./out/forest.png \
  --timeout 180
```

### Edit one image

```bash
python3 scripts/grok_image.py edit \
  "Change only the vase from cobalt blue to coral red; preserve composition, lighting, background, and camera angle" \
  --image ./input/cobalt-vase.jpg \
  --output ./out/coral-vase.png \
  --timeout 180
```

Omit edit `--aspect-ratio` to preserve the source ratio. Source and destination must differ.

## Output contract

Success is one JSON object on stdout:

```json
{
  "ok": true,
  "provider": "grok-build-oauth",
  "action": "generate",
  "output": "/absolute/path/out/forest.jpg",
  "extension": ".jpg",
  "sha256": "...",
  "bytes": 123456,
  "session_id": "..."
}
```

Always use the returned `output` path. The provider controls the real format, so a requested `.png` may return `.jpg`.

Failures are JSON on stderr and include a ready-to-display `user_message`:

```json
{
  "ok": false,
  "provider": "grok-build-oauth",
  "action": "generate",
  "error": "oauth_invalid",
  "message": "Grok OAuth 로그인이 없거나 만료됐어.",
  "fallback_used": false,
  "next_action": "`grok login`으로 로그인한 뒤 다시 요청해 줘.",
  "user_message": "Grok OAuth 이미지 생성 실패 — 원인: 인증 만료. 자동 fallback은 실행하지 않았어. 다음 행동: `grok login`으로 로그인한 뒤 다시 요청해 줘."
}
```

Agents should show `user_message` verbatim and stop.

Exit codes:

- `2`: invalid prompt, arguments, source image, or edit destination
- `3`: Grok CLI or OAuth login unavailable
- `4`: image-tool permission cancelled
- `5`: moderation, provider, or empty-response failure
- `6`: timeout
- `7`: output discovery, copy, or hash-verification failure

## Security and failure guarantees

The wrapper:

- launches only `grok` through the current grok.com OAuth login;
- removes `XAI_API_KEY` from the child environment;
- passes only `image_gen` or `image_edit` through `--tools`;
- adds `--disable-web-search --always-approve`;
- never invokes OpenClaw `image_generate`, Codex, the xAI REST API, or another provider;
- leaves the requested destination untouched on pre-copy failures;
- cleans temporary files after failed copies.

Moderation failures must not be retried with evasive prompt changes.

## Verified examples

Generated at 16:9:

![Grok generated mint teapot on a plum background](examples/e2e-1139-generate.jpg)

Edited to 9:16 with a requested recolor:

![Grok edited orange teapot on a plum background](examples/e2e-1139-edit.jpg)

Machine-readable evidence:

- [`examples/e2e-1139-results.json`](examples/e2e-1139-results.json)
- [`examples/fail-closed-1140-results.json`](examples/fail-closed-1140-results.json)

## Test

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/grok_image.py tests/*.py
```

The final package passes 40 tests covering command construction, OAuth preflight, permission cancellation, timeout, moderation, output isolation, atomic copy, editing safety, portable package layout, documentation links, committed samples, and fresh-session fail-closed evidence.

## Limitations

- Edit V1 accepts one source image.
- Grok chooses exact pixel dimensions and output format for a requested ratio.
- Generation and editing are nondeterministic; visually inspect every result.
- Named real people require a real, consented reference and the edit flow.
- Grok Build CLI output and session layout are external dependencies that may change.

## Documentation

Start with [`docs/README.md`](docs/README.md).

- [`docs/interface-and-routing.md`](docs/interface-and-routing.md) — interface, routing, and contracts
- [`docs/oauth-generation-baseline.md`](docs/oauth-generation-baseline.md) — original OAuth baseline
- [`docs/integration-openclaw-hermes.md`](docs/integration-openclaw-hermes.md) — runtime integration
- [`docs/openclaw-e2e-review.md`](docs/openclaw-e2e-review.md) — generate/edit review evidence
- [`docs/fail-closed-errors.md`](docs/fail-closed-errors.md) — error and no-fallback verification
- [`docs/release-readiness.md`](docs/release-readiness.md) — final readiness summary

## Repository layout

```text
SKILL.md                       Canonical agent workflow
scripts/grok_image.py          Deterministic OAuth wrapper
tests/                         Unit, package, artifact, and fail-closed tests
examples/                      Verified outputs and machine-readable evidence
docs/                          Design and verification records
```
