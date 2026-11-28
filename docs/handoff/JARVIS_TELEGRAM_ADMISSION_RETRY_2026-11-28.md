# Telegram admission-entry reliability follow-up — 28 November 2026

Scope: local bounded repair following PR128 installation; no VPS access, deploy,
Calendar write, paid AI call or merge in this stage. Production last observed
c837c2e at12:33UTC; no current-server claim is inferred from that observation.

Telegram main now constructs TelegramStore, a Store subclass reusing the existing
maintenance_admission.bounded_entry and voice_worker.admission_busy guards.
Only failed transaction __enter__ is retried, max5 attempts with1second delays;
each database attempt retains the existing3second lock/statement limits. Maximum
lock-contention envelope is about19seconds plus local overhead. Successful entry
yields once; handler/body/commit errors propagate without transaction replay.
All TelegramBridge operations use this same instance. No global Store monkeypatch,
new authority, altered SQL lock, schema, lease, source pin or heartbeat semantics.
API/voice/other Store consumers remain unchanged. Exhaustion still fails closed.

Launcher emits a static admission-timeout failure code for an exact matching SQL
shape/state/params, otherwise the existing generic failure code. No exception
message, SQL, params, URL, traceback or credential content is logged. A matching
error code identifies the timeout class, not a promise that it occurred on entry.

Offline boundary tests: exact55P03/57014 retry, failed-session cleanup, bounded
exhaustion, unknown SQL/state/params refusal, body/commit non-replay and safe
failure codes.15tests PASS including existing maintenance-entry tests. Ruff PASS.
Two added real PostgreSQL service cases hold the actual admission lock during
startup or after getUpdates, release after the first real timeout, then assert
one poll, one saved incoming message, one response and valid audit. Local Docker
is unavailable; those two cases require final CI and are not passed locally.
HTTP in those tests is public mock only, never live Telegram acceptance.

PR depends on installed-but-unmerged PR128; retain its code and installation
documentation chain. Deployment requires fresh exact reviewed source approval,
backup capacity reconciliation and stock prepare/inspect/install/postcheck gates.
Do not repeat the historical failed apply, reuse an expired release window,
weaken guards or claim this proves permanent reliability/noisy ASR quality.
Stage2/6 remains incomplete.

## Final verification

Draft PR129: https://github.com/v71369322-lang/ai-command-center/pull/129
Final application HEAD8239478068faac40e7d238e9caf263d83ac03f25;
base PR128/c837c2e54961b72989fe47bf5505f32b01d8bb0e;
merge-ref8fb074bdf197fb31d5e60afdfb0a2e17d4758344.
Head and merge-ref share treee52db3d723935b3c0b3e20149bf3e90296732fb4.
CI46148204798 SUCCESS, both jobs completed successfully:
3036passed/1skipped/1warning in the full PostgreSQL suite, including the two new
real lock-contention service cases; infra1014passed and speech44passed.
These suites overlap and must not be summed. Full source-pinned container smoke,
restart/persistence, isolated restore/audit and runtime boundaries PASS on the
CI merge-ref. This is synthetic cloud evidence, not live Telegram/VPS acceptance.
The actual API for the Telegram integration tests was public mock HTTP.

Local full security_checks.py was blocked before execution by unavailable uv on
PATH; no local PASS claimed. Corresponding full CI security/dependency checks
passed. Local Docker remains unavailable; no PG/container tests claimed locally.
Final checks did not require disabling or changing any failing tests.

Installation requires a new exact release authorization. Last server snapshot
12:33UTC had only12,287,042backup-quota bytes free; do fresh read-only capacity and
retention reconciliation before preparation/install, do not remove more archives
or raise quota from this local development authorization. No server was contacted
in this follow-up. No assertion about current production health beyond the dated
PR128 installation handoff. Original exception-to-PID root-cause attribution remains
unproven; this fix addresses the confirmed exact admission-timeout failure class.
