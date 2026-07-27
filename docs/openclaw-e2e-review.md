# OpenClaw end-to-end verification and review handoff

Date: 2026-07-27
Dudu item: #1139

## Scope

This run verified the installed OpenClaw skill through fresh agent sessions, not only by calling the wrapper directly. It covered generation, editing, aspect ratio handling, provider-corrected output paths, expired OAuth, permission cancellation, and fail-closed behavior.

## Installed package

- Skill: `grok-image-generation`
- OpenClaw source: `openclaw-managed`
- State: eligible, model-visible, user-invocable, and command-visible
- Installed `SKILL.md` and `scripts/grok_image.py` SHA-256 values matched this repository before the run.

## Successful fresh-session flows

### Generate

- OpenClaw session: `3427d725-04c8-4dc0-a481-ac188e41d609`
- Route: `grok-image-generation` → `grok-build-oauth` → native Grok Build `image_gen`
- Ratio: `16:9`
- Requested output suffix: `.png`
- Wrapper-returned suffix: `.jpg`
- Result: 1280×720 JPEG, 188,445 bytes
- SHA-256: `6e6bef8505bb247c566ccfd4b6dd3ac9b349bac1a854ac09a1174dec668b3993`
- Visual verification: one matte mint ceramic teapot on a dark plum background, studio lighting, natural shadow, no text or logo.
- Sample: [`examples/e2e-1139-generate.jpg`](../examples/e2e-1139-generate.jpg)

### Edit

- OpenClaw session: `96fe7008-b0ce-4a1d-841d-bcc1815174fc`
- Route: `grok-image-generation` → `grok-build-oauth` → native Grok Build `image_edit`
- Source: the generated 16:9 sample above
- Requested change: mint teapot to bright orange and canvas to `9:16`; preserve shape, plum background, lighting, shadow, and no-text state
- Requested output suffix: `.png`
- Wrapper-returned suffix: `.jpg`
- Result: 720×1280 JPEG, 156,848 bytes
- SHA-256: `1553faa010d545f5f8ffef1504b56a6f5cebf9f4ce694c1f0a83f827c5909d16`
- Source overwrite check: source and destination remained separate.
- Visual verification: requested recolor and portrait composition succeeded; the teapot shape and scene were preserved.
- Sample: [`examples/e2e-1139-edit.jpg`](../examples/e2e-1139-edit.jpg)

Both sessions parsed and verified the wrapper JSON's returned `output` path. Neither session assumed that the requested `.png` filename existed.

## Fail-closed fresh-session flows

The real grok.com OAuth session was left untouched. Each failure was reproduced with an isolated fake `grok` executable placed first on `PATH`, while the installed wrapper and a fresh OpenClaw session remained real.

### Expired OAuth

- OpenClaw session: `db7802d4-54e4-407c-9fe2-d35616f4796e`
- Simulated preflight: `grok models` returned an expired-login failure.
- Wrapper result: `oauth_invalid`, exit 3
- Output created: no
- Fallback used: no
- Provider calls after failed preflight: none
- Next action: run `grok login`, confirm `grok models`, and retry.

### Permission cancellation

- OpenClaw session: `0165e207-dd41-40fb-8c74-cbd5036b0c77`
- Simulated stream ended with `stopReason: Cancelled` after a successful login preflight.
- Wrapper result: `permission_cancelled`, exit 4
- Output created: no
- Fallback used: no
- The command included `--tools image_gen --disable-web-search --always-approve`.
- Next action: verify headless approval settings and retry.

The harness also set an `XAI_API_KEY` sentinel. The wrapper removed it from the Grok child environment and did not call another provider.

## Execution record

Machine-readable results are in [`examples/e2e-1139-results.json`](../examples/e2e-1139-results.json). Verification included:

- fresh `openclaw agent --session-id ... --json` sessions for generate, edit, OAuth failure, and permission failure;
- wrapper-returned path, action, provider, byte count, and SHA-256 checks;
- `file` and `sips` format/dimension checks;
- direct visual inspection of both samples;
- source/destination collision check;
- fake CLI call-count checks proving no provider call after invalid OAuth and exactly one image-tool attempt before cancellation.

The final Discord handoff attaches the two exact verified result files from the OpenClaw workspace, proving they are readable by the attachment path.

## Remaining limitations

- Editing V1 accepts one local JPEG, PNG, or WebP source image.
- Supported ratios are `auto`, `1:1`, `16:9`, `9:16`, `4:3`, and `3:4`; Grok chooses the exact pixel dimensions.
- The provider controls the generated file format. Callers must use the wrapper-returned path because a requested `.png` may become `.jpg`.
- Image generation and editing are nondeterministic, so every result still needs visual review.
- OAuth and permission failures were safely simulated; the test deliberately did not expire or revoke the real account session.
- Named real people still require a real, consented reference and the edit flow.

## Reviewer checklist

- [ ] Open both attached images in Discord.
- [ ] Confirm the generate sample is 16:9 and matches the mint-teapot prompt.
- [ ] Confirm the edit sample is 9:16, orange, and preserves the original scene.
- [ ] Confirm the committed JPEG hashes match `examples/e2e-1139-results.json`.
- [ ] Confirm the requested `.png` paths were not reported as results; the returned `.jpg` paths were used.
- [ ] Confirm OAuth/permission failures show cause, no fallback, and a next action.
- [ ] Mark Dudu #1139 done only after review approval.
