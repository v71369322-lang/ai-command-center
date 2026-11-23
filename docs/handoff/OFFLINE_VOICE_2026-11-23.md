# Offline voice continuation, 23 November 2026

Owner scope: make ordinary Telegram voice intake usable without paid AI while
Google Calendar onboarding waits for their return. Owner-defined sections will
follow; do not invent classifications, grant project execution, or infer Google
consent. Google Cloud for the calendar account is paused at initial terms/country
selection. No Google API credentials or consent were created.

## Base and implementation

Branch `codex/offline-voice-intake-20261123`, parent local documentation commit
`dd95fc30531c674ec1a865dfbea030aa31af6538`, source predecessor PR102 exact
`9f6297baba3f89a1ffa5fdc879dedfdd7bbb8f7c`. Origin fetched; main remains
`f5ff8b2757b1b759b08a173fdac9d3e51f84d227`. PR102 OPEN/DRAFT and both existing
workflows 43599473922/43599473966 SUCCESS rechecked in this session. They are not
CI for the new code. New PR must target `codex/telegram-offline-release`, retaining
the unmerged dependency chain. No merge or extra worktree.

Implemented exact Telegram voice downloader, separate opt-in worker, local pinned
CPU/int8 speech decoding, existing owner transcript readback composition, replay
protection for distinct callback updates, configured transport support for exact
transcript keyboard, and accurate removal of processed voices from pending count.
No Task/grant/provider spending/publication/Google event is created. The optional
speech image/dependency group is independent of the API/poller dependency set.
See [worker contract](../telegram/OFFLINE_VOICE_WORKER.md).

## Current evidence

- Real local model `Systran/faster-whisper-base` exact snapshot
  `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`, reviewed file manifest in
  `deploy/speech-base-model.json`. Synthetic Windows Irina voice, 4.214 seconds:
  `Завтра в 15 часов позвонить поставщику.` recognized correctly, elapsed7.88s
  including model load. Model downloaded once anonymously, no paid API or owner
  audio used. This is not VPS speed/quality acceptance.
- Optional-runtime tests: 19 passed, including real PyAV decode/resampling and
  actual-duration-over-limit rejection. Tests with mocked inference do not count
  as genuine recognition; the preceding separate model smoke does.
- Ruff all src/tests/scripts, API export and coding-tool export checks PASS.
  Changed production modules have no Bandit findings. Optional speech dependency
  audit reports no known vulnerabilities; speech export matches uv.lock.
- Local PG tests are run in the owned synthetic DB/helper. Initial broader runs
  reached 87/88 passing cases but were blocked first by missing Redis (then fixed
  with a confined owned Redis container/LF launcher), then by the helper lacking
  Docker CLI/socket for two pre-existing actual-executor service cases. These
  overlapping partial runs are not added together or claimed complete. The final
  bounded suite explicitly excludes those two container cases; full CI must run
  them normally. Latest bounded PG result: **116 passed, 2 deselected** (69.08s),
  adding immutable intake-audit binding to the downloaded file checks. Three
  additional pure tests cover pause vs fatal integrity/profile errors.
  New PR/CI are recorded in the PR/checkpoint, not inferred.
- Windows full `security_checks.py` was blocked by its POSIX `npm` invocation
  (npm.cmd is not an executable accepted by that subprocess call). No check was
  disabled or vulnerability ignored. Full retained gate remains required in CI.

## Read-only VPS check this session

Existing SSH channel to 176.12.75.135 used for diagnostics only, then closed.
Both deployment/activation `phase=VERIFIED`, source9f6297b; seven existing services
running, Telegram up5hours. Hardware: 4 vCPU, 7837MiB RAM, 4779MiB available,
3918MiB swap (183MiB used), 41GiB free disk. Resource headroom appears plausible
for a separately bounded base-model worker, but actual runtime memory/latency
must be measured. No upload, install, restart, image/config/credential/profile
change, new daemon or production audio download performed.

## Remaining activation work (not completed)

The current VPS prepare/install adapter does not yet include this additional
speech service. It must be extended/reviewed through existing exact release
interlocks before production activation; an ad hoc container/service is not an
acceptable shortcut. Prepare the model as a read-only artifact, exact-source
speech image, protected disabled profile with explicit cutoff, scoped existing
Telegram/DB mounts, resource limits and inspect/postcheck/revocation checks.
Then obtain exact-version installation authorization, activate once, and observe
one genuine owner voice -> readback -> confirmed saved request. Mock tests and a
local model run do not establish that this works in the live bot.

Current paid AI restriction persists. Google terms/access need the owner's real
confirmation on return. The original poller transient-failure availability issue
and observed slow audit-heavy replies are not silently declared fixed here.
