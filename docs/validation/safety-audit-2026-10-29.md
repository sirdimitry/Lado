# Input safety audit after the reported freeze

The existing 53 tests pass, but they do not establish resilience to input-service
failures. Fifteen new isolated checks exercise the adapter with all native service
objects replaced. Four controls pass and eleven safety requirements fail against
the unchanged 0.1.0 source. These are eleven failed checks, not eleven proven
independent root causes of the system freeze.

| Required behaviour | Result |
| --- | --- |
| Timeout leaves interception disarmed | FAIL |
| User-requested tap disable is respected | FAIL |
| 1000 timeout notifications cannot cause a restart loop | FAIL |
| Next key after timeout passes without reading its text | FAIL |
| Key callback does not enter synchronous editor focus RPC | FAIL |
| Callback exception immediately disconnects/disarms tap | FAIL |
| Revoked posting permission prevents event submission | FAIL |
| Unsupported atomic editor replacement never falls back to synthetic typing | FAIL |
| Failed atomic replacement never falls back to synthetic typing | FAIL |
| Maximum-size selection never falls back to synthetic typing | FAIL |
| Stop removes the run-loop source | FAIL |
| Secure-field state prevents reading key text | PASS |
| Own tagged event bypasses detection | PASS |
| Mouse click passes through and clears context | PASS |
| Supported atomic replacement does not post keys | PASS |

Run on macOS with Python 3.11+ and the project dependencies:

```sh
.venv/bin/python -m unittest discover -s tests -p test_incident_safety.py -v
```

These are release gates with normal failing assertions. They are not skipped or
marked `expectedFailure` to produce a green result. They must pass after fixes.
The macOS adapter checks skip on other platforms, so the existing Linux-only CI
does not enforce these gates; a macOS job will be needed before the next release.

Safety scope: no app launch, global event tap, posted events, AX access, network,
or real blocking waits in the new tests. Only public synthetic text is used.
The unresponsive-editor case uses an immediate timeout trap rather than hanging a
real editor; the large-selection case intercepts the synthetic-typing entry point
instead of generating 131072 native events.

Limitations: this audit does not reproduce a whole-system freeze, prove its exact
cause, or establish safety under real editor stalls, long sessions or multiple
simultaneous switchers. No live test was performed. Installed application and DMG
remain unchanged. Lado stays stopped with its login agent disabled.

Raw incident diagnostics are private local files under `build/incident-2026-10-29/`
and must not be committed or published.

## Source fixes after the audit

All fifteen gates now pass. Total: **82 automated checks pass**. The observer is
listen-only; no production keyboard event submission remains. AX queries and edits
run after the event callback returns. A 16-event queue and 250 ms expiry, fresh
focus/security checks, input serial and deadline checks cancel stale operations.
Unsupported or failed atomic edits are skipped; Return/Tab always pass unchanged.
Timeouts and exceptions latch the tap off until process restart. Stop disconnects
the run-loop source, and a zero-content advisory file lock excludes duplicate
installed/source instances. The CI matrix now includes macOS and Linux.

The old reversal test now exercises the supported atomic AX path; its former
expectation of a synthetic-key fallback was intentionally removed. No safety gate
was skipped or marked expectedFailure. Additional tests cover deferred edits,
newer keys, editor timeout traps, stale events, focus/security/permission changes,
overflow, passive tap creation, restart latching and lock release/symlink rejection.

**No new native live test, installed replacement or DMG release has been performed.**
The earlier native test report does not validate this new architecture. A passive
observer avoids holding the system input pipeline, but isolated tests cannot prove
whole-system stability. The exact cause of the earlier freeze remains unresolved.
