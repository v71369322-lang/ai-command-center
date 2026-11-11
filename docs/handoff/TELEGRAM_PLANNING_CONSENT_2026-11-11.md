# Telegram planning consent checkpoint — 11 November 2026

- Repository: v71369322-lang/ai-command-center. Actual main fetched/checked;
  f5ff8b2757b1b759b08a173fdac9d3e51f84d227 remains canonical.
- Dependency: Draft PR #88, feat/planning-reviewed-f1-approval,
  39b71bdde2ff9f8dcecf73fc41b17b5c959fd7c2. Its CI was still running at the
  initial check; do not infer SUCCESS from local tests or from parent #87.
- Current branch: feat/telegram-planning-consent, based on #88. The new Draft
  PR must target that dependency until it is merged. No merges or retargeting.
- Scope: `/plan_authorize NUMBER`, exact delivered review card, owner callback,
  atomic card-consumption hook into the existing reviewed F1 approval. Pinned
  operator-evidence loader is disabled by default and contains no credentials.
  See [contract and boundaries](../telegram/PLANNING_AUTHORIZATION.md).
- Existing planning task idempotency key was factored into request_key without
  changing its value. New callback prefix is pa:, admitted only with the exact
  planning label/keyboard by the existing transport. Existing F1, ledger,
  lease/fence/source and delivery unknown-outcome behavior are preserved.
- Local validation uses the dedicated acc-codex-planning PostgreSQL project,
  pinned Linux Python image, frozen uv.lock and a read-only source mount. No
  production/other-project data or credentials are used. Provider/Bot API are
  MockTransport fixtures; these tests are not live AI or Telegram acceptance.
- Core locked Linux/PG scope: 251 passed / one existing Starlette warning.
  API contract matches under locked Linux dependencies. A check using the
  unpinned Windows .venv reported drift; contracts and lockfiles were preserved.
  Full Ruff and git diff --check passed. Adding help entries initially exceeded
  the existing 8192-byte transport cap; concise descriptions preserve that cap.
  Final menu/help delivery scope: 29 passed / one existing warning after this
  bounded repair. This is reported separately from the core scope, not added
  to repeated runs. The dedicated local test DB was stopped after validation.
- No VPS connection/change this turn. No production approval/grant, paid call,
  deployment, merge, new credential or profile activation. The owner's live
  waiting task is not approved by local tests. Current bot does not receive
  these new commands automatically.
- Next safe step: protected live planning gateway/runtime integration with
  authority and money admission immediately before I/O, durable INTENT before
  network, one exact request key, and advisory draft acceptance only. Preserve
  unknown-outcome/no-retry semantics. Real operator model/tariff/funding evidence,
  credential binding, exact source/images/deployment and paid consent remain
  separately gated; none may be guessed or activated by an enabled flag.
- Final commit, Draft PR, source/merge-ref CI and validation counts accompany
  the resulting PR. Retain the preceding VPS reconciliation and owner phone
  acceptance checkpoints as dated evidence, not as current server probes.
