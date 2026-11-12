# Plan content acceptance checkpoint

Branch `codex/plan-acceptance` depends on Draft #96, exact parent
`67443ae297ed0d49de8d9086fd3347e054ad8231`. Origin was fetched; main remains
`f5ff8b2757b1b759b08a173fdac9d3e51f84d227`. Initial tree was clean, no worktree
created. Parent exact CI 43180091558 was freshly rechecked SUCCESS. The original
handoff was read from `origin/docs/local-codex-handoff-20261107`; its file does
not exist in this current branch, so no old deployment state was substituted.

The handoff's next sequence is owner plan acceptance → isolated coding →
verifier → Draft PR. This bounded step implements content acceptance only:
owner API preview, exact-digest acceptance and CURRENT/STALE readback on the
existing PG/Control/audit path. Latest current, question-free Command Center
draft and complete setup declarations are required. Request/context/source,
plan document/version/provenance and setup/repository declarations are pinned.
Concurrent/restarted exact retries produce one receipt; all references and
flags are semantically checked on read. Setup history is validated once within
the same locked read, with no cross-transaction cache or trust-prefix shortcut.

Acceptance stores only bounded references in the existing append-only audit.
No Task/Approval/ExternalGrant/Outbox, provider/key access, spending, coding,
verification, publication, resume or deployment is created. All such authority
flags remain false. Receipt freshness means exact current content, never
execution readiness. Imported draft provenance is not upgraded. Other projects
remain outside this acceptance scope. Existing password/OIDC CSRF and owner
identity checks remain in force; no second authority mechanism is introduced.

Three additive API paths/methods are reviewed in OpenAPI. Locked Linux rendering
matches the generated UTF-8 contract. New tests include PG concurrency,
staleness/setup/source changes, role/CSRF checks, rollback, capacity, strict input,
audit corruption and resealed semantic tampering. Final local targeted scope:
192 passed in the locked Linux/PostgreSQL acceptance + request review/manual
drafts/storage/planning suite. Earlier overlapping runs are not added. Exact
full CI is recorded in the resulting dependent Draft PR.
Ruff and existing Bandit LOW-rule triage passed without security-gate changes.

Updated the prior latency checkpoint from pre-install assumptions to actual
recorded installation-session evidence: #96 is installed, both journals
VERIFIED, owner `/help` approximately 10 seconds / server receive→SENT 6.844
seconds. No new VPS probe or change was made in this content-acceptance stage.
Private account/profile details remain outside Git.

Remaining: Telegram observed content-confirmation/UI, then independently bounded
coding preparation with real repository capability and F1 permissions. This
receipt alone authorizes none of it. No live provider test has been performed;
paid Telegram consent and deployment continue to require separate exact owner
decisions. New acceptance API is not deployed by this development task.
