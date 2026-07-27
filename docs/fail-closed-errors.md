# Grok OAuth fail-closed errors

Date: 2026-07-27
Dudu item: #1140

## Policy

A Grok OAuth image request keeps its selected provider, quality path, and billing path. If Grok authentication or execution fails, the wrapper stops immediately. It does not invoke OpenClaw `image_generate`, Codex image generation, the xAI REST API, `XAI_API_KEY`, or another provider.

Every stderr payload retains diagnostic fields and adds one unified user-facing field:

```text
Grok OAuth 이미지 생성 실패 — 원인: <인증 만료/권한 취소/timeout/moderation/기타>. 자동 fallback은 실행하지 않았어. 다음 행동: <조치>.
```

Edit failures use `Grok OAuth 이미지 편집 실패` with the same reason, no-fallback statement, and next action. Agents must return `user_message` verbatim and stop.

## Failure mapping

| Wrapper error | User reason | Exit | Next action |
| --- | --- | ---: | --- |
| `oauth_invalid` | `인증 만료` | 3 | Run `grok login`, confirm `grok models`, and retry. |
| `permission_cancelled` | `권한 취소` | 4 | Check headless approval and retry. |
| `timeout` | `timeout` | 6 | Retry later or increase `--timeout`. |
| `moderation_blocked` | `moderation` | 5 | Modify the prompt safely; never evade the block. |
| Other wrapper/provider errors | `기타` | existing code | Follow the payload's `next_action`. |

## Fresh OpenClaw session verification

The working skill was installed as the OpenClaw-managed `grok-image-generation` skill. Four fresh agent sessions loaded that skill and executed its installed wrapper through isolated fake `grok` executables. The real grok.com login was not expired, revoked, or modified.

### OAuth expired

- Session: `a9bb8ed2-c84e-43dd-b79a-a9699c1e1779`
- Calls: one `grok models` preflight; no image-tool call
- Exit/error: 3 / `oauth_invalid`
- Output: none
- Delivered message:

  > Grok OAuth 이미지 생성 실패 — 원인: 인증 만료. 자동 fallback은 실행하지 않았어. 다음 행동: `grok login`으로 로그인한 뒤 다시 요청해 줘.

### Permission cancelled

- Session: `6a795022-a0ce-47ed-a28c-e37d573ccc68`
- Calls: login preflight plus exactly one `image_gen` attempt
- The attempt included `--tools image_gen --disable-web-search --always-approve` and returned `stopReason: Cancelled`.
- Exit/error: 4 / `permission_cancelled`
- Output: none
- Delivered message:

  > Grok OAuth 이미지 생성 실패 — 원인: 권한 취소. 자동 fallback은 실행하지 않았어. 다음 행동: headless 실행의 승인 설정을 확인한 뒤 다시 시도해 줘.

### Timeout

- Session: `548e86e8-2749-457c-84ad-3cee97606ee8`
- Calls: login preflight plus exactly one timed-out `image_gen` attempt
- Exit/error: 6 / `timeout`
- Output: none
- Delivered message:

  > Grok OAuth 이미지 생성 실패 — 원인: timeout. 자동 fallback은 실행하지 않았어. 다음 행동: 잠시 후 다시 시도하거나 `--timeout` 값을 늘려 줘.

### Moderation

- Session: `bdc0ebd1-9743-4671-a940-ed4baa29ae62`
- Calls: login preflight plus exactly one blocked `image_gen` attempt
- Exit/error: 5 / `moderation_blocked`
- Output: none
- Delivered message:

  > Grok OAuth 이미지 생성 실패 — 원인: moderation. 자동 fallback은 실행하지 않았어. 다음 행동: 차단을 우회하지 말고 다른 안전한 방향으로 프롬프트를 수정해 줘.

## No-fallback evidence

For all four cases:

- `fallback_used` was `false`;
- the requested output did not exist;
- the fake CLI logs contained only `models` and, after a valid preflight, one native `image_gen` command;
- logs contained no `image_generate`, Codex, `api.x.ai`, or leaked `XAI_API_KEY` sentinel;
- the OpenClaw final response exactly matched the wrapper's `user_message`.

The executable CLI test in [`tests/test_fail_closed.py`](../tests/test_fail_closed.py) reproduces all four cases and checks exit codes, call counts, output absence, environment stripping, unified messages, and forbidden fallback tokens. Machine-readable fresh-session results are in [`examples/fail-closed-1140-results.json`](../examples/fail-closed-1140-results.json).
