# Reviewed planning approval checkpoint — 11 November 2026

- Repo: v71369322-lang/ai-command-center, clean parent branch reviewed/fetched.
- Canonical main remains f5ff8b2757b1b759b08a173fdac9d3e51f84d227.
- Dependency/base: Draft PR #87, feat/trusted-planning-profile,
  4fb0aa5e447de6c90b5e013ff899b12f8e074827. Its exact HEAD CI run 42957343198
  completed SUCCESS; merge-ref previously verified as
  41f2280bbaf632d40888008df7adad4723700b0e.
- Current branch: feat/planning-reviewed-f1-approval. PR must target the parent
  branch until that dependency is merged; no automatic retarget or merge.
- Owner Telegram screenshots confirm resume and planning request 131179169,
  command-center, task f3ac4e07-c72e-4f47-9149-bfdb21e3207e, v1 WAITING_APPROVAL.
  Old project card was rejected without changing the already selected project.
  This is phone evidence, not a new independent database inspection.
- Local edits: planning_approval.py, shared Gateway.check_budget extraction,
  PG integration tests, STATUS and planning documentation. See
  [contract and limitations](../planning/REVIEWED_F1_APPROVAL.md).
- Validation: 123 passed in isolated local Linux/PG with frozen uv.lock; full
  Ruff and git diff --check passed. Actual targeted tests include concurrency,
  rollback, quote expiry, profile/context mutation, shared budget/funding,
  unknown outcome, grant reuse and production dispatch rejection. They do not
  perform real provider I/O. Existing deprecation warning remains.
- Docker Desktop was started locally to supply Linux. Dedicated project
  acc-codex-planning hosts the synthetic test database; no other project's
  sources, data or container settings were changed. No VPS login/change this
  turn. New production intents, grants, reservations and paid calls: none.
- Next safe step: implement and test an observed owner Telegram review/confirm
  flow around this internal boundary, retaining the existing card delivery and
  F1 authority mechanisms. Then protected live profile/key/runtime integration;
  no activation from an enabled flag alone. A deployment or real paid call
  still needs separate concrete owner approval. Current live task is not to
  be approved automatically by this local development work.
- Final commit/PR and exact source/merge-ref CI are recorded by the resulting
  Draft PR. Preserve this checkpoint; do not treat local tests as live runtime
  or provider acceptance.
