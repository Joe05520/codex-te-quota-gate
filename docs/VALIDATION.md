# Validation — v0.3.1, 2026-11-01

## Verified locally

Environment: macOS, Python 3.12.5. Offline tests do not require Codex on PATH.

`python3 -m unittest discover -s tests -v`: **42 tests passed**. Parameterized subcases cover:

- Either-window trigger; 14%, 14.99%, exactly 15%, 0%, 100%.
- Same synthetic session: sufficient → low 5h → reset/sufficient → low weekly.
- 90-second snapshot expiry, future timestamps and already-passed reset times.
- Missing, malformed, duplicate or different-bucket quota data.
- Invalid numeric values, booleans, NaN and infinity.
- Primary/secondary reversal; selection by duration and billing bucket.
- Redaction by allowlist: unrelated synthetic account fields are discarded.
- Real subprocess RPC handshake against a scripted app-server peer; notifications handled,
  incoming approval request rejected, no thread/turn/model requests sent.
- RPC timeout, malformed JSON, error responses and bounded subprocess cleanup.
- Forced safe settings override contrary inherited environment variables.
- Dedicated TE state directory; atomic private snapshot permissions.
- Missing/corrupt/stale snapshots do not forward hooks; collector failure invalidates snapshots.
- Emergency disable, nested-sidecall suppression, bootstrap digest mismatch.
- Upstream nonzero exit, malformed/non-object output, hook timeout; hook stdout stays JSON.
- Generated marketplace events, hook runner, source-change detection and revision rejection.
- SessionEnd host limit is 3 seconds; a real sleeping upstream is terminated within that limit.
- Independent 5-hour/weekly thresholds, equality boundaries, zero-to-disable-window semantics.
- Excluded roots/children, similar-prefix neighbors, symlink aliases, and duplicate paths.
- Settings changed without rebuilding: threshold, exclusion and re-enable affect forwarding.
- Generated marketplace runner reads the same settings saved by the GUI backend.
- GUI static files, state/save/preview APIs, persisted settings, stale-save rejection.
- Invalid settings do not overwrite existing data; malformed settings keep hooks inactive.
- GUI Host, Origin and per-process token checks; non-demo mode rejects simulation requests.
- Demo CLI refuses explicit runtime file overrides to avoid overwriting live settings/snapshots.

`node --check quota_gate/web/app.js`: passed.

Evidence: [test output](offline-tests.txt), [threshold demo](demo.txt).

## Browser GUI acceptance

The actual localhost GUI was operated in the in-app browser using synthetic data:

- Changed 5h threshold to 25 and weekly threshold to 10, saved, reloaded, and observed persistence.
- Added a synthetic project, left participation off, and verified its child directory is excluded.
- Added another synthetic project, enabled participation, and verified low-quota eligibility.
- Switched to the low-5h demo scenario and observed the eligible state.
- Verified non-demo mode displays unavailable quotas as inactive and hides simulation controls.
- Browser warning/error log was empty at the checks.

Screenshots: [threshold controls](gui-overview.png), [project controls and preview](gui-projects.png).
These screenshots contain synthetic names and `/demo/` paths, not user repositories.
This synthetic browser acceptance does not establish actual hook execution. Separate local integration
checks below cover live quota reading and hook discovery.

## Verified against real upstream source, offline

Pinned upstream: `microsoft/TokenEconomizer@e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9`.

`python3 scripts/check_upstream.py --source /path/to/TokenEconomizer` confirmed:

- Actual upstream configuration resolves to envfacts/off/off/off despite contrary file settings.
- Actual `InjectionConfig(profile="envfacts").paid` is false.
- A marketplace can be built from the clean pinned checkout.
- An inactive generated hook returns `{}` and creates no upstream TE state.

Evidence: [sanitized upstream check](upstream-check.json).

The active-branch contract is exercised with a fake upstream bootstrap, not a paid agent.
The source check does not establish that real session logs will yield useful envfacts.

## Local integration check, 2026-11-01

- Installed v0.2.1 through the bundled Codex CLI plugin commands.
- Live `account/rateLimits/read` returned the selected quota windows without creating a model turn.
- `hooks/list` found five enabled hooks, with no warnings or errors; SessionEnd reports 3 seconds.
- Existing shared settings were preserved. Hook trust was not changed.
- Machine paths, account/quota values and installation receipts remain local and are not published.

## Not established

- Desktop hook trust or execution in a live desktop conversation.
- Real envfacts learning and later injection from actual user sessions.
- Quota savings, latency of the real account endpoint, quality equivalence, or research utility.
- Windows integration or accounts that lack a 5-hour quota window.

No model API, subscription reset, plugin install, permission approval or private research data
was used for the offline test suite. The separate authorized integration check installed the plugin
and read live quotas, without approving hook trust or starting a model turn. The shipped reader can perform a live quota query only
when the user explicitly runs `capture` or `watch` with their Codex client.

GitHub Actions separately runs the offline suite and JS syntax check on Linux/macOS with Python 3.10/3.12. See
the repository Actions page for actual remote run outcomes; local evidence is not remote CI.

## v0.3.0 additional checks

- Sanitized bounded receipts distinguish skipped/forwarded/context-returned, never persist payload data.
- Receipt write failures do not change hook results; absent observations remain unknown.
- Native backend demo cannot overwrite live runtime and exits when its parent closes stdin.
- Read-only hooks RPC reports trust and strips command/source metadata.
- Upstream progress JSON lines preserve the final additionalContext result.
- Native Swift/AppKit/SwiftUI app compiled locally and ad-hoc signature verified.

Real low-quota forwarding after user trust and actual context consumption remain unproven.

The existing trusted v0.2.1 plugin was intentionally retained during a live threshold crossing.
The native monitor can observe eligibility/trust immediately; detailed receipts require the
explicit v0.3.0 upgrade and a new hook review. No live execution was synthesized for evidence.

## v0.3.1 recovery and observation checks

- Preserved the existing installed v0.3.1 plugin: five trusted, enabled hooks; no load problems.
- 42 offline tests passed, including observation-state distinctions and diagnostic/live isolation.
- Actual installed Codex CLI with a loopback-only canned response completed an ephemeral turn.
  SessionStart, UserPromptSubmit, Stop and SessionEnd produced diagnostic receipts; there was
  no tool call, so no PostToolUse was expected. No paid model was called.
- The actual pinned upstream bootstrap was tested in a temporary directory: sufficient quota
  skipped it; low quota called it; no cached facts returned no context; a cached synthetic fact
  returned hook-specific context. Receipt counts were 3 checked / 2 forwarded / 1 context.
- These diagnostics do not establish normal intervention in the current desktop conversation,
  host consumption of the returned content, learning quality or quota savings.
- Native panel sizing/scrolling and close/quit shortcuts are checked separately on the local app.

Native v0.3.1 acceptance on the target Mac confirmed: the window stays within the visible
screen, the close button/Esc/Cmd+W hide the panel while the status item remains, and Cmd+Q
terminates the app and its owned Python monitor. Receipts for these checks stay local.
