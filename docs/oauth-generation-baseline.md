# Grok OAuth Image Generation Baseline

Dudu item: #1132  
Verified: 2026-07-27 KST  
Environment: Grok Build 0.2.112, default model `grok-4.5`

This document fixes a reproducible baseline for Grok Build image generation through the logged-in grok.com session. It does not use the xAI REST API.

## Preconditions

```bash
command -v grok
grok --version
grok models
```

Expected authentication line:

```text
You are logged in with grok.com.
```

For the baseline commands, remove `XAI_API_KEY` from the child environment explicitly:

```bash
env -u XAI_API_KEY grok ...
```

Grok debug output must resolve credentials as:

```text
auth_type=SessionToken
```

Together, these checks distinguish the grok.com OAuth/session path from API-key authentication.

## Test prompt

```text
Use image_gen to generate a 1:1 test image of one matte blue cube centered on a light gray studio floor, soft shadow, no text. Return the image path.
```

## Failure baseline: headless execution without approval

Command:

```bash
mkdir -p /tmp/grok-oauth-baseline

env -u XAI_API_KEY grok \
  -p 'Use image_gen to generate a 1:1 test image of one matte blue cube centered on a light gray studio floor, soft shadow, no text. Return the image path.' \
  --tools image_gen \
  --disable-web-search \
  --output-format streaming-json \
  --debug \
  --debug-file /tmp/grok-oauth-baseline/failure-debug.log \
  > /tmp/grok-oauth-baseline/failure-events.jsonl \
  2> /tmp/grok-oauth-baseline/failure-stderr.log
```

Observed final streaming event:

```json
{
  "type": "end",
  "stopReason": "Cancelled",
  "sessionId": "019fa12c-0f2a-7773-bb1e-98129650ca4e",
  "num_turns": 1
}
```

Observed debug result:

```text
"stopReason":"cancelled"
"cancellationCategory":"PermissionCancelled"
```

Observed constraints:

- No image was created for the failed session.
- stderr was empty.
- Grok CLI exited with status `0` even though the request was cancelled.
- Therefore, process exit status and empty stderr are not sufficient success checks.
- The wrapper must parse the streaming `end` event and reject any final `stopReason` other than `EndTurn`.

## Success baseline: restricted image tool with approval

Minimal reproducible command:

```bash
mkdir -p /tmp/grok-oauth-baseline

env -u XAI_API_KEY grok \
  -p 'Use image_gen to generate a 1:1 test image of one matte blue cube centered on a light gray studio floor, soft shadow, no text. Return the image path.' \
  --tools image_gen \
  --disable-web-search \
  --always-approve \
  --output-format streaming-json \
  --debug \
  --debug-file /tmp/grok-oauth-baseline/success-debug.log \
  > /tmp/grok-oauth-baseline/success-events.jsonl \
  2> /tmp/grok-oauth-baseline/success-stderr.log
```

Why each safety flag is present:

- `--tools image_gen`: allow only the requested image operation.
- `--disable-web-search`: prevent unrelated network research during generation.
- `--always-approve`: allow the native image tool in non-interactive/headless mode.
- `--output-format streaming-json`: provide a stable final event and session ID for parsing.

Observed final streaming event:

```json
{
  "type": "end",
  "stopReason": "EndTurn",
  "sessionId": "019fa12c-bfce-7e53-b900-38180cd6aeea",
  "num_turns": 4
}
```

Observed debug evidence (home and canonical working directory normalized):

```text
auth_type=SessionToken
image saved to disk path=$HOME/.grok/sessions/<encoded-canonical-cwd>/019fa12c-bfce-7e53-b900-38180cd6aeea/images/1.jpg bytes=151859
```

Verified artifact:

```text
format: JPEG/JFIF
width: 1024
height: 1024
bytes: 151859
sha256: 2253b9893452ff9b425d8a3a45018c65f8ea2bce940c149df2abcf924b00b1c7
```

Verification commands:

```bash
SESSION_ID='019fa12c-bfce-7e53-b900-38180cd6aeea'
ENCODED_CWD="$(python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.path.realpath(os.getcwd()), safe=""))')"
IMAGE="$HOME/.grok/sessions/$ENCODED_CWD/$SESSION_ID/images/1.jpg"

test -s "$IMAGE"
file "$IMAGE"
sips -g pixelWidth -g pixelHeight -g format "$IMAGE"
shasum -a 256 "$IMAGE"
```

The session ID and hash above identify this baseline run; future runs will produce different values.

## Event interpretation

A successful run requires all of the following:

1. The process finishes before the wrapper timeout.
2. A valid JSONL event with `type: "end"` exists.
3. The final event has `stopReason: "EndTurn"`.
4. The event supplies a non-empty `sessionId`.
5. The matching session directory contains a non-empty image.
6. The result passes image format and dimension checks.

A failed run includes any of:

- missing final `end` event;
- `Cancelled`, including `PermissionCancelled`;
- timeout;
- moderation/provider failure;
- `EndTurn` without a session-scoped image;
- unreadable or empty image output.

Grok Build 0.2.112 may emit intermediate `use_tool` errors while trying to load its bundled Imagine guidance, then continue to a successful `image_gen` call. Do not fail on an intermediate diagnostic alone. Decide success from the final event plus the verified session-scoped artifact.

## Output location constraint

Grok stores generated images under:

```text
~/.grok/sessions/<percent-encoded-canonical-cwd>/<session-id>/images/<number>.jpg
```

Important details:

- Grok uses the canonical working directory. If the working path contains symlinks, encode the path returned by `pwd -P`, not the shell's logical path.
- The final JSONL `sessionId` identifies the current run.
- Do not choose the globally newest file; concurrent runs can make that incorrect.
- Resolve the canonical current directory with `pwd -P`, percent-encode it, then combine it with the final session ID.
- If multiple images exist in the current session, use the tool result/order rather than another session's file.

## Authentication and fallback constraints

- The baseline was executed with `env -u XAI_API_KEY`.
- Grok resolved `auth_type=SessionToken`.
- The wrapper must never read `~/.grok/auth.json` directly; Grok Build owns token storage and refresh.
- If `grok models` no longer reports grok.com login, stop and request `grok login`.
- Do not fall back to `XAI_API_KEY`, OpenClaw `image_generate`, Codex image generation, or another provider.
- Report the cause, state that no fallback ran, and provide the next action.

User-facing authentication failure example:

```text
Grok OAuth 이미지 생성 실패 — 원인: 로그인 만료.
자동 fallback은 실행하지 않았어.
다음 행동: `grok login` 후 다시 요청해 줘.
```
