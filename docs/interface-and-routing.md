# Grok Image Skill: Interface and Routing

Status: design baseline for Dudu item #1131  
Target: Grok Build 0.2.112 using a grok.com OAuth session

## 1. Decision

This skill wraps Grok Build's native `image_gen` and `image_edit` tools. It does not call the xAI REST API and does not require or read `XAI_API_KEY`.

The selected path is:

```text
OpenClaw request
  -> skill wrapper
  -> Grok Build CLI
  -> grok.com OAuth session
  -> image_gen or image_edit
  -> local image copied to the requested output path
```

The wrapper must fail closed. If OAuth, permissions, generation, editing, moderation, or output discovery fails, it reports the error and stops. It must not silently fall back to OpenClaw `image_generate`, Codex image generation, or an xAI API key.

## 2. Preconditions

Before execution:

1. `grok` is available on `PATH`.
2. `grok models` succeeds and reports `You are logged in with grok.com.`
3. Grok Build exposes the requested native tool.
4. The destination directory is writable.
5. For edits, the source image exists and is readable.

Current verified environment:

- Grok Build: `0.2.112`
- Authentication: grok.com session token
- Default model: `grok-4.5`
- Bundled skill: `~/.grok/bundled/skills/imagine/SKILL.md`
- Native tools: `image_gen`, `image_edit`

## 3. Public wrapper interface

The implementation should expose one executable with two subcommands:

```bash
python3 scripts/grok_image.py generate PROMPT [OPTIONS]
python3 scripts/grok_image.py edit PROMPT --image SOURCE [OPTIONS]
```

### 3.1 Generate

```bash
python3 scripts/grok_image.py generate \
  "A glossy red sphere floating above a matte white floor" \
  --aspect-ratio 1:1 \
  --output ./out/red-sphere.jpg
```

Inputs:

| Argument | Required | Default | Rules |
| --- | --- | --- | --- |
| `PROMPT` | yes | — | Non-empty UTF-8 text. Preserve a user-supplied final prompt verbatim. |
| `--aspect-ratio` | no | `auto` | Initial allowlist: `auto`, `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. |
| `--output` | no | `./grok-image-<timestamp>.jpg` | Resolve to an absolute path; create parent directories. |
| `--timeout` | no | `180` seconds | Kill the child process and return a timeout error when exceeded. |
| `--events` | no | disabled | Optional path for sanitized Grok streaming JSON, for diagnosis. |

Grok tool payload represented in the agent prompt:

```json
{
  "tool": "image_gen",
  "prompt": "<PROMPT>",
  "aspect_ratio": "<ASPECT_RATIO>"
}
```

### 3.2 Edit

```bash
python3 scripts/grok_image.py edit \
  "Change only the sphere from red to blue; preserve composition and lighting" \
  --image ./input/red-sphere.jpg \
  --output ./out/blue-sphere.jpg
```

Inputs:

| Argument | Required | Default | Rules |
| --- | --- | --- | --- |
| `PROMPT` | yes | — | Describe the requested transformation and what must remain unchanged. |
| `--image` | yes | — | V1 accepts one absolute or resolvable local image path. |
| `--aspect-ratio` | no | omitted | A single-image edit preserves the source aspect ratio. |
| `--output` | no | `./grok-edit-<timestamp>.jpg` | Resolve to an absolute path; create parent directories. |
| `--timeout` | no | `180` seconds | Same behavior as generation. |
| `--events` | no | disabled | Same behavior as generation. |

Grok tool payload represented in the agent prompt:

```json
{
  "tool": "image_edit",
  "prompt": "<PROMPT>",
  "image": "<ABSOLUTE_SOURCE_PATH>"
}
```

Multi-image editing is outside V1. Add it only after the single-image path is verified end to end.

## 4. Grok CLI invocation

### Generate

```bash
grok -p "<tool-directed prompt>" \
  --tools image_gen \
  --disable-web-search \
  --always-approve \
  --output-format streaming-json
```

### Edit

```bash
grok -p "<tool-directed prompt with absolute source path>" \
  --tools image_edit \
  --disable-web-search \
  --always-approve \
  --output-format streaming-json
```

Rules:

- Restrict `--tools` to exactly the requested image tool.
- `--always-approve` is required for non-interactive execution; without it, the tested headless request ended with `PermissionCancelled`.
- `--disable-web-search` prevents unrelated tool use. If factual grounding is required, OpenClaw performs research before invoking this wrapper.
- Do not pass `--model` in V1. Use the authenticated Grok Build default, currently `grok-4.5`, and record the observed model in diagnostics.
- Capture stdout and stderr separately. Never parse human prose as the only success signal.

## 5. Output contract

The wrapper prints exactly one final JSON object to stdout.

Success:

```json
{
  "ok": true,
  "provider": "grok-build-oauth",
  "action": "generate",
  "output": "/absolute/path/to/result.jpg",
  "session_id": "<grok-session-id>"
}
```

Failure:

```json
{
  "ok": false,
  "provider": "grok-build-oauth",
  "action": "generate",
  "error": "oauth_expired",
  "message": "Grok OAuth image generation failed: login expired.",
  "fallback_used": false,
  "next_action": "Run `grok login` and retry."
}
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Image produced, copied, and verified at `output`. |
| `2` | Invalid arguments or missing source image. |
| `3` | Grok CLI unavailable or OAuth login invalid. |
| `4` | Permission cancelled or native image tool unavailable. |
| `5` | Moderation or provider generation failure. |
| `6` | Timeout. |
| `7` | Generated output could not be located, copied, or verified. |

A successful result requires all of the following:

1. Grok ends normally.
2. The current run's session ID is captured from the streaming `end` event.
3. The image associated with that session is located under the corresponding `~/.grok/sessions/.../<session-id>/images/` directory.
4. The image is copied to `--output`.
5. The destination exists, is non-empty, and is recognized as an image.

Do not select a globally newest image because concurrent runs can make that incorrect.

## 6. OpenClaw routing

Use this skill when the user explicitly asks for any of:

- Grok image generation
- Grok Imagine
- Grok Build image generation or editing
- xAI image generation through the logged-in Grok subscription/OAuth session

Provider routing:

| User intent | Route |
| --- | --- |
| Explicit Grok, Grok Imagine, xAI OAuth, or Grok Build | This skill |
| Explicit Codex or OpenAI through Codex OAuth | `codex-image-generation` |
| Explicit OpenClaw/native image tool | OpenClaw `image_generate` |
| Explicit xAI API key/API billing | Not this skill; use a separately approved API client |
| No provider preference | Preserve OpenClaw's existing default; do not silently make Grok the default |

Tool routing inside this skill:

- No source image -> `generate` -> `image_gen`
- Source image or request to alter an existing result -> `edit` -> `image_edit`
- Named real person -> require a real reference and use `image_edit`
- Exact charts, tables, diagrams, or substantial text -> build with code instead of an image model

## 7. Failure and notification policy

There is no automatic provider or authentication fallback.

User-facing message template:

```text
Grok OAuth 이미지 생성 실패 — 원인: <인증 만료/권한 취소/timeout/moderation/기타>.
자동 fallback은 실행하지 않았어.
다음 행동: <grok login 후 재시도/권한 확인/프롬프트 수정>.
```

Editing errors replace `이미지 생성` with `이미지 편집`.

On moderation failure, do not retry with paraphrasing intended to evade the block. On OAuth failure, do not read or use `XAI_API_KEY`. On any Grok failure, do not invoke another image provider unless the user makes a new explicit request.

## 8. OAuth path versus xAI API-key path

| Property | This skill | xAI REST API |
| --- | --- | --- |
| Entry point | Grok Build CLI | `https://api.x.ai/v1/images/...` |
| Authentication | grok.com OAuth/session token managed by Grok Build | `XAI_API_KEY` bearer token |
| Billing/entitlement | Grok account/CLI entitlement | xAI API account |
| Image operation | Native `image_gen` / `image_edit` tools | Image generation/editing endpoints |
| Secret handling | Wrapper never reads a token file directly | Client must read and protect an API key |
| Fallback relationship | None | None |

The two paths are separate products and must not be treated as interchangeable.

## 9. Acceptance criteria for implementation

A fresh session using only this document must be able to:

1. Implement the two-subcommand wrapper without adding API-key support.
2. Generate a new image through grok.com OAuth.
3. Edit one local source image through grok.com OAuth.
4. copy the correct session-scoped result to the requested path.
5. Return the stable JSON and exit-code contract.
6. Stop and notify without fallback for authentication, permission, timeout, moderation, or output errors.
7. Route explicit Grok, Codex, native OpenClaw, and API-key requests without ambiguity.
