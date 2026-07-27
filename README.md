# Grok Image Generation Skill

Generate images through Grok Build's native `image_gen` tool using the current grok.com OAuth session.

## Requirements

- Grok Build CLI on `PATH`
- `grok models` reports `You are logged in with grok.com.`
- Python 3.9+

The wrapper removes `XAI_API_KEY` from the child environment and does not call the xAI REST API.

## Generate

```bash
python3 scripts/grok_image.py \
  "A paper-cut forest at dawn, soft layered shadows, no text" \
  --aspect-ratio 16:9 \
  --output ./out/forest.jpg
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

The Grok subprocess is restricted to `image_gen`, runs with web search disabled, and uses non-interactive approval so the image call can complete in headless mode.

Design and verified baseline details:

- [`docs/interface-and-routing.md`](docs/interface-and-routing.md)
- [`docs/oauth-generation-baseline.md`](docs/oauth-generation-baseline.md)
