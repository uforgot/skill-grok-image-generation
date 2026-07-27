# Grok Image Skill

Generate and edit images through Grok Build's native `image_gen` and `image_edit` tools using the current grok.com OAuth session.

## Requirements

- Grok Build CLI on `PATH`
- `grok models` reports `You are logged in with grok.com.`
- Python 3.9+

The wrapper removes `XAI_API_KEY` from the child environment and does not call the xAI REST API.

## Agent skill package

[`SKILL.md`](SKILL.md) is the canonical OpenClaw/Hermes agent workflow. Install or mount this repository as one skill directory so `SKILL.md` and `scripts/grok_image.py` keep their relative layout. The skill routes only explicit Grok/Grok Imagine/xAI OAuth requests here; native OpenClaw and Codex requests keep their own providers.

The package does not assume a live OpenClaw or Hermes installation path.

## Generate

```bash
python3 scripts/grok_image.py generate \
  "A paper-cut forest at dawn, soft layered shadows, no text" \
  --aspect-ratio 16:9 \
  --output ./out/forest.jpg \
  --timeout 180
```

Supported aspect ratios:

```text
auto, 1:1, 16:9, 9:16, 4:3, 3:4
```

Successful stdout:

```json
{"ok": true, "provider": "grok-build-oauth", "action": "generate", "output": "/absolute/path/out/forest.jpg", "extension": ".jpg", "sha256": "...", "bytes": 123456, "session_id": "..."}
```

The wrapper binds the result to the current Grok session ID and the `images/...` path returned in that run's streaming events. It copies through a temporary file and atomically replaces the destination, then verifies the SHA-256 hash. The source format is preserved: if `--output` has a different extension, the returned path is corrected to the generated extension.

The Grok subprocess is restricted to `image_gen`, runs with web search disabled, and uses non-interactive approval so the image call can complete in headless mode. The original command without the `generate` subcommand remains supported for compatibility.

## Edit one image

```bash
python3 scripts/grok_image.py edit \
  "Change only the vase from cobalt blue to coral red; preserve composition, lighting, background, and camera angle" \
  --image ./input/cobalt-vase.jpg \
  --output ./out/coral-vase.jpg \
  --timeout 180
```

V1 accepts one readable local JPEG, PNG, or WebP source. The wrapper validates the file signature, resolves the absolute source path, and passes it only to native `image_edit`. The source aspect ratio is preserved when `--aspect-ratio` is omitted. Source and output paths must differ so an edit cannot silently overwrite its reference.

The edit prompt is reference-first: apply only the requested change and preserve everything else. For a named real person, use a real, consented reference and follow Grok's safety policy.

Successful edit stdout uses the same output metadata with `"action": "edit"`.

## Errors

Before generation or editing, the wrapper verifies that `grok models` reports an active grok.com login. Failures are printed as JSON to stderr:

```json
{"ok": false, "provider": "grok-build-oauth", "action": "generate", "error": "oauth_invalid", "message": "Grok OAuth 로그인이 없거나 만료됐어.", "fallback_used": false, "next_action": "`grok login`으로 로그인한 뒤 다시 요청해 줘."}
```

Exit codes:

- `2`: invalid prompt, arguments, source image, or edit destination
- `3`: Grok CLI or OAuth login unavailable
- `4`: image tool permission cancelled
- `5`: moderation, provider, or empty-response failure
- `6`: timeout
- `7`: output discovery, copy, or hash verification failure

The destination is only replaced after a complete image has been copied to a temporary file. Timeout and provider failures leave the requested output untouched; copy failures remove temporary files. No provider or API-key fallback is attempted.

Design and verified baseline details:

- [`docs/interface-and-routing.md`](docs/interface-and-routing.md)
- [`docs/oauth-generation-baseline.md`](docs/oauth-generation-baseline.md)
- [`docs/integration-openclaw-hermes.md`](docs/integration-openclaw-hermes.md)
- [`docs/openclaw-e2e-review.md`](docs/openclaw-e2e-review.md)
