# F2 validation record

## Executed evidence

Clean source commit `b7b5c33cddab9ed161a7c0cc9ed35517c2812d68`,
2026-10-24, isolated cloud environment, synthetic fixtures only:

| Check | Actual result |
|---|---|
| `scripts/verify_cloud.sh` | PASS, including all stages below |
| Python regression suite | **140 passed**, including 25 F2 coding cases |
| Infrastructure tests / Ruff | **32 passed** / PASS |
| Ruff `src tests scripts` | PASS |
| TypeScript / Vite | PASS |
| OpenAPI snapshot comparison | PASS |
| Python dependency audit | 64 resolved dependencies, **0 known advisories** |
| npm audit | **0 known advisories** |
| Bandit | 0 MEDIUM/HIGH; 27 retained, reviewed LOW findings |
| Current runtime-secret scan / Git whitespace | PASS; not a universal secret detector |
| Mobile Chromium, 390 × 844 | PASS: login, start F2, failed/passed checks, open mock draft; no horizontal overflow; existing XSS check retained |
| Real broker / two isolated coding stages | PASS: Git edit, failed first checks, autonomous repair, independent replay, mock PR |
| F2 runtime negatives | PASS: repeated cancel, total deadline, lost watchdog; no accepted PR/restart; unknown usage remains reserved |
| Failed acceptance | PASS: failed test history, readable report and actual synthetic units persist, no PR |
| Real API / worker container smoke | PASS: API, PG, Outbox, Redis, worker, scoped broker and verifier |
| API / worker / broker restart | PASS: F1 result and cancel intent preserved, new task accepted; F2 uses the same durable lifecycle |
| Worker SIGKILL / watchdog drill | PASS: independent stop, confirmed absence, no orphan, exact resume only for new work |
| Encrypted backup / isolated PG restore | PASS: different networkless container, audit/interlock verified |
| Runtime boundaries | PASS: API/worker without Docker socket; trusted broker/watchdog explicitly retain it |

The full suite emitted one upstream `StarletteDeprecationWarning` concerning
`httpx` in TestClient. It is retained, not filtered or described as a failed test.
The follow-up changes the failed-check UI label so it does not claim a repair
occurred when attempts were exhausted. CI for `70419fc` then failed the existing
memory probe: exit 137 was observed but immediate Docker inspect returned
`OOMKilled=false` (139 other tests passed). This was not waived. The probe now
retains the container for a bounded three-second wait for asynchronous OOM
evidence; it **still requires both exit 137 and OOMKilled=true**. Deterministic
regressions check delayed evidence and timeout without inventing OOM success.
The actual memory test and both new regressions passed locally. Final-head CI
reruns the browser test and complete pipeline, including all 142 Python cases.
PR #13 checks are the authoritative final-head
CI status: <https://github.com/v71369322-lang/ai-command-center/pull/13/checks>.
Do not equate an earlier green run with validation of a later head.
GitHub also emits a Node 20 action-runtime deprecation warning for inherited
pinned actions, which it runs with Node 24; this is separate from the Node 22
application build. The warning is retained rather than hidden.

## Concrete synthetic outcome

`scripts/coding_smoke.py` executed the real container path with no manual step
between admission and completion. Baseline SHA:
`a41d5fdf083fa0a162299b74ac9c155b58b140cb`.

1. Actual Git commit `2619496760126ecfc9a027cf88a8318efb2b0af7`:
   four acceptance tests, **two failures**.
2. Actual repair commit `7987cede8267a7a42165cafa4de680d405182ae0`:
   four tests, **zero failures**.
3. Second networkless container reconstructed both revisions and reran both
   checks. The broker accepted the matching proof and persisted the mock draft.
4. `published=false`, `url=null`; no remote fixture branch/PR was created.

Evidence files under ignored `.runtime/`: `f2-final-verification.log`,
`test-results.xml`, `coding-smoke.json`, `security-summary.json`,
`all-pip-audit.json`, `npm-audit.json`, `bandit.json`, `mobile.png`, and inherited
restart/restore/watchdog evidence. They are local run artifacts, not independent
offsite audit checkpoints. No runtime secret values are committed.

## Defects found and addressed during development

- Dependency gate rejected the initial Dulwich 0.25.2 (14 reported advisories).
  Updated to locked **1.2.19**; repeated all-dependency audit found zero known
  advisories. No vulnerability exemption was added.
- Independent Git verification now rejects unreachable extra objects, forged
  checks/checksums/revisions/branches and invalid usage counters.
- Failure paths retain acceptance history instead of losing failed tests.
- Watchdog/operator stop reconciliation retains uncertain coding reservations;
  a stopped container is not treated as proof of zero provider usage.
- Sequential sandbox handoff resets observed-start evidence under the launcher
  lock, preventing previous-stage absence from confirming a new stage's stop.
- Draft fetching respects the current login generation; logout clears drafts.
  Verifier mode does not import the agent/provider implementation.

## Boundaries and remaining gates

Only **MockProvider** is enabled. Actual file changes, Git commits, tests, two
containers and persistence are real; AI reasoning is not. Responses and GitHub
REST adapters use HTTP MockTransport tests only. No real credentials, paid calls,
Codex session, remote publication or external cancellation were tested.

The GitHub adapter's test journal is synthetic; production activation requires
durable PG intent/reconciliation, authorized remote branch publication and
scoped credential/repository policy. Real model pricing/usage reconciliation and
provider compatibility remain separate gates. See [implementation](IMPLEMENTATION.md).

Cloud Docker tests use explicit `cloud-rootful-test`. Rootless user namespaces,
systemd/cgroup delegation, host compromise resistance, VPS resource capacity,
real VPN/HTTPS/MFA, offsite backup/checkpoint retention and independent external
watchdog remain **NOT VERIFIED**. RPO ≤15 minutes / RTO ≤4 hours remain provisional.
F2-specific container SIGKILL during every possible repair/verification boundary
and live provider reconnect behavior are not exhaustively fault-injected; shared
F1 restart/lease/cancel safety tests do not prove arbitrary real-agent resumability.

Conclusion: the bounded **synthetic** coding cycle is demonstrated. This is not
full F1 acceptance, authorization to deploy, or readiness for real CRM coding.
