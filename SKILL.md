---
name: grok-image-generation
description: "Generate or edit images with Grok Build native tools through a grok.com OAuth session. Use only when the user explicitly requests Grok, Grok Imagine, xAI OAuth, or Grok Build."
---

# Grok image generation

Use the bundled wrapper for Grok OAuth image generation and single-image editing. Resolve `<skill-dir>` as the directory containing this `SKILL.md`; never assume an OpenClaw workspace path, Hermes path, or current working directory.

## Route first

Use this skill only when the user explicitly asks for Grok, Grok Imagine, xAI through an existing Grok login/OAuth session, or Grok Build image generation/editing.

- Explicit Grok/Grok Imagine/xAI OAuth/Grok Build → this skill.
- Explicit Codex/OpenAI OAuth → `codex-image-generation`.
- Explicit OpenClaw/native image provider → OpenClaw `image_generate`.
- Explicit xAI API key or REST billing → a separately approved API client, not this skill.
- No provider preference → preserve the current OpenClaw default; do not silently choose Grok.

Never fall back to another provider, API key, or tool after a Grok failure. Do not read or pass `XAI_API_KEY`.

## Preconditions

1. `grok` is on `PATH`.
2. `grok models` reports `You are logged in with grok.com.`
3. Python 3.9 or later is available.
4. The destination directory is writable.
5. An edit source is one readable local JPEG, PNG, or WebP file.

The wrapper performs the Grok login preflight and source validation. If preflight fails, stop and report its JSON error and `next_action`.

## Choose the action

- No source image → `generate` → native `image_gen`.
- Existing source, recolor, restyle, add/remove, extend, or iterate → `edit` → native `image_edit`.
- Named real person → require a real, consented reference and use `edit`; never synthesize their likeness from text alone.
- Exact text, numbers, charts, tables, or technical diagrams → build with code instead of an image model.

If the user supplies a detailed final prompt, preserve it verbatim. Otherwise write a concise 2–5 sentence prompt. For edits, describe only the requested change and what must remain unchanged.

## Generate

```bash
python3 "<skill-dir>/scripts/grok_image.py" generate \
  "A paper-cut forest at dawn, soft layered shadows, no text" \
  --aspect-ratio 16:9 \
  --output ./out/forest.jpg \
  --timeout 180
```

Supported ratios: `auto`, `1:1`, `16:9`, `9:16`, `4:3`, `3:4`.

The legacy form without the `generate` subcommand is accepted, but new calls should use the explicit subcommand.

## Edit one source image

```bash
python3 "<skill-dir>/scripts/grok_image.py" edit \
  "Change only the vase from cobalt blue to coral red; preserve composition, lighting, background, and camera angle" \
  --image ./input/cobalt-vase.jpg \
  --output ./out/coral-vase.jpg \
  --timeout 180
```

Omit `--aspect-ratio` to preserve the source ratio. V1 accepts one source image. The output must not overwrite the source, including after extension correction.

## Execution guarantees

The wrapper:

- restricts Grok to exactly `image_gen` or `image_edit`;
- passes `--disable-web-search --always-approve`;
- removes `XAI_API_KEY` from the child environment;
- captures streaming JSON and requires a normal `EndTurn`;
- resolves the image using this run’s session ID and event path, never a globally newest file;
- copies atomically, preserves the generated extension, and verifies SHA-256;
- defaults to a 180-second timeout.

Success is one JSON object on stdout:

```json
{"ok":true,"provider":"grok-build-oauth","action":"generate","output":"/absolute/result.jpg","extension":".jpg","sha256":"...","bytes":123456,"session_id":"..."}
```

Use the returned `output` path, not the originally requested filename, because Grok’s generated extension is preserved. Open or inspect the final image. Confirm the requested edit or composition before reporting success, then return or attach that exact file.

## Failure handling

Failures are JSON on stderr with `ok: false`, an `error`, diagnostic `message`, `fallback_used: false`, `next_action`, and a unified user-facing `user_message`.

Show `user_message` verbatim to the user. Its format is:

```text
Grok OAuth 이미지 생성 실패 — 원인: <인증 만료/권한 취소/timeout/moderation/기타>. 자동 fallback은 실행하지 않았어. 다음 행동: <조치>.
```

Edit failures use `이미지 편집 실패` in the same format.

- Exit 2: invalid prompt, ratio, source, or destination.
- Exit 3: missing Grok CLI or invalid/expired grok.com OAuth login.
- Exit 4: image-tool permission cancelled.
- Exit 5: moderation, provider, or empty-response failure.
- Exit 6: timeout.
- Exit 7: result discovery, copy, or hash verification failure.

On any failure:

1. Return `user_message`, which already states the cause, no-fallback decision, and `next_action`.
2. Stop. Do not invoke another image provider unless the user makes a new explicit request.

On moderation failure, do not retry or paraphrase to evade the block. Timeout/provider failures leave the requested destination untouched; failed copies clean their temporary files.

## Troubleshooting

- `oauth_invalid` → run `grok login`, confirm `grok models`, then retry.
- `permission_cancelled` → confirm headless approval settings and that the wrapper still supplies `--always-approve`.
- `timeout` → retry once only when appropriate or increase `--timeout`; do not start another provider.
- `invalid_source` → provide one valid readable JPEG, PNG, or WebP local path.
- `output_missing` / `ambiguous_output` → keep one image-tool call per wrapper invocation and inspect the reported Grok session.
- `copy_failed` → check destination permissions and disk space.
