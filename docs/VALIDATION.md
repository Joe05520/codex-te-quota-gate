# Validation — 2026-10-31

## Verified locally

Environment: macOS, Python 3.12.5. No live Codex CLI was present on PATH.

`python3 -m unittest discover -s tests -v`: **18 tests passed**. Parameterized subcases cover:

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

Evidence: [test output](offline-tests.txt), [threshold demo](demo.txt).

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

## Not established

- Live `account/rateLimits/read` authentication in the target environment.
- Successful manual marketplace installation, desktop hook trust, or a live desktop session.
- Real envfacts learning and later injection from actual user sessions.
- Quota savings, latency of the real account endpoint, quality equivalence, or research utility.
- Windows integration or accounts that lack a 5-hour quota window.

No model API, subscription reset, plugin install, permission approval or private research data
was used for the recorded local tests. The shipped reader can perform a live quota query only
when the user explicitly runs `capture` or `watch` with their Codex client.

GitHub Actions separately runs the offline suite on Linux/macOS with Python 3.10/3.12. See
the repository Actions page for actual remote run outcomes; local evidence is not remote CI.
