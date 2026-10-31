# Data flow and permissions

## Offline demo and tests

- Synthetic quota values, fake session identifiers and temporary source trees only.
- Tests launch local Python subprocesses to simulate Codex RPC and an upstream hook.
- No model calls, personal conversation reads, subscription resets, installs, or purchases.

## Explicit live quota reader

- Launches the chosen `codex app-server` in stdio mode with TE hooks disabled for that process.
- Sends only initialization and `account/rateLimits/read`. It never starts a thread or turn.
- The official Codex process uses its existing authenticated account to request usage data.
  This is network access through the official client, not an offline quota calculation.
- Requests from the server are rejected; this client does not approve actions or perform login.
- Discards stderr and unrelated/raw account fields. Writes only schema version, observation time,
  selected limit bucket, window lengths, percentages and reset times to the specified snapshot.
- Snapshot writes are atomic, mode 0600. A newly created parent directory is mode 0700.
  Permissions of an existing parent directory are not silently changed.
- No telemetry or third-party HTTP client exists in the wrapper.

## Local GUI and project choices

- GUI HTTP server binds to 127.0.0.1 only. It loads local packaged HTML/CSS/JS; no CDN/fonts.
- It reads only the explicitly selected settings and quota files. There is no directory scan.
- User-entered project paths are canonicalized (which can resolve symlink metadata), not crawled.
- It writes independent thresholds, master toggle and project name/path/exclusion entries to
  a private local JSON settings file. Runtime settings are ignored by git.
- Demo has a separate runtime and generates synthetic snapshots; it never reads an account.
- APIs need a per-process token; modifying requests also need the exact local Origin. Host
  checking and CSP limit cross-site access. This is not protection against other trusted local
  programs with the same filesystem access. Access logs are disabled.
- Project exclusions control new hook forwarding by cwd; they do not erase history or redact
  existing mixed-project transcripts. No content-erasure or data-isolation guarantee is made.

## Explicit upstream hook connection

- Hook payloads, including their transcript references, are passed to upstream in memory via stdin.
  The wrapper does not log them. Upstream reads session data for its envfacts functionality.
- The wrapper sets an independent `TOKENECONOMIZER_HOME` to `te-state` alongside the snapshot.
  Upstream's private state may contain session-derived commands/errors and must not be published.
- The reviewed source config confirms the envfacts-only profile has no paid proposer, while
  loopguard and repomap are disabled. This is not a guarantee about arbitrary upstream versions.
- Previously injected facts remain part of your conversation and may later be sent to your
  selected model service, just like the other context in that conversation.
- Generated marketplaces record absolute machine paths and are intentionally ignored by git.

## GitHub publication

Only wrapper source, synthetic tests, documentation and offline validation evidence belong in
the public repository. Never commit runtime snapshots, generated marketplaces, upstream learned
state, tokens, account identifiers, private research files, or real conversation logs.

## v0.3.0 local observation

The menu-bar monitor reads only quota snapshots, shared settings and sanitized hook receipts.
It performs the read-only `hooks/list` and quota RPCs, never a turn or model request. Receipts
retain time/event/result/duration/context-present metadata, 40 recent items and recorded counts.
They exclude prompts, answers, injected text, session IDs and project paths; writes are private
and best effort. Existing upstream envfacts storage remains governed by the upstream profile.
The native app uses the existing Python installation and adds no login item.
