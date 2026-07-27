# Documentation

This directory separates design decisions from runtime verification. Start with the package [`README`](../README.md) for installation and normal use.

## Core design

- [`interface-and-routing.md`](interface-and-routing.md)
  - Public generate/edit interface
  - Grok CLI command restrictions
  - Output and failure contracts
  - OpenClaw routing versus API-key paths

- [`oauth-generation-baseline.md`](oauth-generation-baseline.md)
  - Initial grok.com OAuth verification
  - Why `--always-approve` is required in headless runs
  - Streaming event and session-output behavior

## Runtime integration

- [`integration-openclaw-hermes.md`](integration-openclaw-hermes.md)
  - OpenClaw managed-skill installation
  - Hermes local-skill loading
  - Fresh-session routing verification
  - Codex and native provider isolation

## End-to-end evidence

- [`openclaw-e2e-review.md`](openclaw-e2e-review.md)
  - Real generation and editing sessions
  - Aspect-ratio and returned-path verification
  - Committed sample hashes
  - Reviewer checklist

- [`fail-closed-errors.md`](fail-closed-errors.md)
  - Unified user-facing errors
  - OAuth, permission, timeout, and moderation simulations
  - Proof that no other provider or API path was called

- [`release-readiness.md`](release-readiness.md)
  - Final package status
  - Installation and test summary
  - Remaining limitations

## Machine-readable evidence

- [`../examples/e2e-1139-results.json`](../examples/e2e-1139-results.json)
- [`../examples/fail-closed-1140-results.json`](../examples/fail-closed-1140-results.json)

The evidence files contain no OAuth token or API key. Failure tests use isolated fake `grok` executables and sentinel values; the real grok.com session remains intact.
