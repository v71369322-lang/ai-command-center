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
Stage2/6 remains incomplete. Final source/merge-ref CI evidence will follow.
