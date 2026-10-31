# Integration and rollback

This is an opt-in local integration, not an installer. Demo/test work never registers a plugin.

## GUI and shared settings

Run `python3 -m quota_gate gui --open` to edit local settings. Run with `--demo` for a
separate synthetic runtime, without touching the regular settings/snapshot. The GUI never
installs the hook or queries an account. Existing `capture` / `watch` commands populate the
quota snapshot separately. The page clearly shows that live integration is unverified.

`threshold_5h` and `threshold_weekly` are independently adjustable between 0 and 100. Zero
disables triggering from that window; both quota windows must still be valid. Unknown windows
are not treated as sufficient quota. `enabled=false` disables forwarding for all projects.

Projects contain a display name, canonical absolute directory path, and `excluded` boolean.
An excluded root also excludes descendants; a more specific participating entry does not
override an excluded ancestor. Any matching exclusion wins. Entries at separate worktree or
clone paths are independent. The GUI does not enumerate directories, read source files, or
discover repositories automatically. Invalid configuration makes hooks inactive.

Each hook checks the shared settings file at invocation. Changes do not retract context,
delete learned state, or stop an already-running upstream fold. Matching uses hook `cwd`,
not individual transcript contents: do not use this feature as redaction for a conversation
that moves between multiple projects. Keep one project per conversation.

The GUI listens only on loopback, uses a per-process API token and exact Origin/Host checks,
and writes snapshots/settings atomically with mode 0600. Use one GUI process for each settings
file; stale saves from another tab in the same process are rejected with a reload message.

## Upgrading from v0.1.0

Source checkout users can pull v0.2.0 and launch the GUI without installing anything.
If you previously installed a generated v0.1.0 marketplace, its copied Python does not gain
this functionality from a source pull alone. After review, generate a **new** marketplace
directory with v0.2.0, specifying `--settings runtime/settings.json` and the same quota path.
Manually re-register/re-add the plugin and review changed hooks in the target Codex environment.
Do not enable old and new wrappers simultaneously. No automatic migration/trust is performed.

After a v0.2.0 bundle is connected, threshold/project changes only need a GUI save; no rebuild.
For custom paths, launch GUI with the same explicit `--settings` and `--snapshot` paths.

## Before connecting real hooks

1. Review the generated hook file and `gate-config.json` locally. They contain your paths;
   do not upload generated marketplaces or runtime data to GitHub.
2. Use the same explicit Codex CLI / CODEX_HOME / logged-in account context for the reader
   and the host running your conversations. A different binary or account may report different
   buckets. Do not copy credentials into this project.
3. The unwrapped upstream plugin must not remain enabled alongside this wrapper. Otherwise
   its separate hooks can run regardless of this gate. Inspect your installed plugins/hooks;
   disable the standalone upstream plugin yourself before connecting this wrapper.
4. If upstream previously pruned tools, restore them with upstream's `toolprune restore`
   **before removing or disabling that installation**. Review project config afterwards.
   The wrapper does not rewrite your project config or silently remove existing restrictions.
5. Give each account/environment a separate private runtime path. Keep `te-state` private.
6. Run `capture` once and inspect `evaluate` before manually installing generated hooks.
7. Review and trust the new hook through the host UI. No automatic trust or permission override.

No Codex CLI was available on PATH in the development environment. Desktop hook loading has
not been accepted in a live conversation. The app-server client was verified with a scripted
protocol peer; live sign-in and desktop behavior require a later acceptance test.

## What can be changed

The wrapper itself writes only explicit snapshot/build output paths. The upstream code, once
enabled, keeps learned facts, ledger, launchers and session-derived state in `te-state` next to
the snapshot. The source Python hashes are verified on every generated-hook call. This is not
a sandbox: manually connecting hooks authorizes trusted upstream Python to run on your machine.

The wrapper never changes Codex model selection, tool availability, or trust settings. Its
four forced TE environment settings override upstream global/repository configuration at the
pinned version. An independent original plugin or commands run outside the wrapper are outside
the gate. A privileged user changing the wrapper/config can also change its behavior.

## Stop and remove

1. Stop `watch` with Ctrl+C. It invalidates the snapshot. If it was killed abruptly, delete only
   the specific snapshot file or wait up to 90 seconds; reset timestamps also force inactivity.
2. In the target environment, manually remove the wrapper plugin:

   ```bash
   codex plugin remove te-quota-gate@te-quota-gate
   codex plugin marketplace remove te-quota-gate
   ```

3. Review whether the local generated marketplace and `runtime/te-state` are still needed.
   Remove only those explicitly chosen paths. There is no broad recursive cleanup command.
4. Existing conversation history and already-started upstream background folds are not erased
   or terminated. Start a new conversation if you need context without earlier injected facts.

Emergency bypass for hooks started with an environment you control: `TE_DISABLE=1`.
The wrapper respects this flag even when quotas are low. For desktop hosts, disable the wrapper
in the plugin/hook UI; do not assume an environment variable set in a later terminal updates an
already running desktop process.
