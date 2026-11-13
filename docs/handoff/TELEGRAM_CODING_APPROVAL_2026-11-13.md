# Telegram offline coding approval / readback

Branch `codex/telegram-coding-approval` depends on Draft #99 at exact
`68a9405c2dac7e6cb057c61f198a028645edb59b`. Origin fetched, initial tree clean;
main still f5ff8b2. Parent PR and workflow 43211082081 were freshly checked:
OPEN/DRAFT, SUCCESS, 2325 application + separate 1013 infra tests. No worktree,
merge, server operation, deployment, provider spending or live Telegram call.

Adds `/coding_authorize UUID`: original intake freezes exact existing waiting-task
identity. Full baseline files/tests, complete replacement diff and fixed scope/
isolation/checks are paginated before a bounded observed owner execution card.
Nonce/message/profile/connection/source/intake and all exact queued/observed SENT
parts are rechecked. Card expires after 300 seconds from receipt; ordinary F1
approval expires after at most 120 seconds and no later than the card deadline.
Atomic locked composition reuses the same F1 approval/Outbox. Card consumption
and reply roll back with expiry/revocation/failure. No separate authority, financial
grant, AI adapter, remote access, publishing or execution is performed by the UI.

Adds `/coding_status UUID` because existing generic status is deliberately scoped
to synthetic tests. Readback requires original task creation/hash/profile/source;
success additionally requires exact report, artifact hash and verifier anchor.
Normal stop/stale content does not make status resume or authorize a task. Existing
cancel/stop, source pinning, broker/rootless/lease/fence/watchdog behavior preserved.

Local initial regression 126 passed before status guards. Later scope 129 passed
with status/revocation/profile cases. Final expanded scope 204 passed, one existing
actual-container case excluded from the local helper (no daemon/image there).
All local scopes overlap and are not added. Final exact source/CI
evidence is recorded in the resulting dependent Draft PR. Ruff, unchanged API
contract and retained Bandit LOW triage were checked; final checks must match HEAD.
Project reassignment is an ordinary stale-card refusal with an explicit reply,
not a silent rejected update. The final regression includes this metadata-only case.
New commands stay inside existing text/transport limits. No real Telegram/VPS/
rootless execution acceptance is claimed. Local Docker Desktop was started for
the already-owned PostgreSQL test environment; other projects were not changed.

Remaining separately authorized steps: actual rootless deployment/acceptance,
real AI code proposal consent/adapter, remote repository fetch/access/publication.
No historical provider profile/deployment window was read, renewed or assumed valid.
Workflow: [TELEGRAM_CODING_APPROVAL.md](../planning/TELEGRAM_CODING_APPROVAL.md).
