# Telegram response budget and Calendar wording

Scope: owner requested continuing the agreed Jarvis2.0 route toward the usable
assistant, and keeping overall progress clear. Current phase2/6 is not complete.
[Stable overall route](../jarvis-2/ROADMAP.md). Base8160817/PR114 full CI passed
(45433386782 and45433386877); do not rebase the dependent chain onto main.

## Evidence and bounded change

The installed7edc1d8 real Calendar query previously took53.31s UI→SENT and24.60s
inbox→SENT, versus3.10s signed Google HTTP. A fresh read-only cgroup inspection
confirmed Telegram still had NanoCpus250000000 and memory268435456, running the
expected81d54072 image. Counters: usage2172476776us, throttled6143225717us,
85389 throttled periods out of91888. This confirms CPU throttling; it does not
prove all queue/audit latency is caused by CPU or guarantee a particular new speed.

New optional release field `telegram_cpu: 1` enables a bounded one-core Telegram
budget only in assistant-only releases with Telegram. Memory256MiB, pids32,
read-only mounts, networks, stop/backup/approval/audit/owner checks remain unchanged.
No additional daemon/service/model/API permission. Invalid types, booleans,0,
values above1 or scope without assistant/Telegram are rejected.

Absence retains legacy0.25CPU and exact old compose rendering. This is essential:
changing the default globally would invalidate the installed predecessor's bundle.
Existing1CPU budget is preserved by future assistant updates unless an explicit
supported value is provided. The candidate and preparation hashes pin the setting.
Stock prepare accepts --telegram-cpu1; inspect reconstructs and rechecks the target.
Actual runtime proof rejects a changed NanoCpus value, including reversion to0.25.

Explicit read-only Calendar aliases now include «что у меня завтра в календаре?»,
«что у меня в календаре сегодня», «покажи календарь на завтра» and «покажи расписание
на сегодня», with basic punctuation/spacing normalization. No substring routing:
mixed requests or add/move/delete wording are not silently interpreted as reads.
This is bounded phrase support, not a claim of unrestricted AI understanding.

## Validation

55 Linux release checks passed: CPU budget, Calendar candidate/custody/runtime,
assistant candidate and operator regressions.58 real-PostgreSQL focused Telegram,
Calendar runtime/write-policy and assistant policy checks passed, including the
formerly unsupported wording through the real intake path with mock Google HTTP.
These do not constitute a real Google call or production timing test.
Ruff passed. New final HEAD/merge-ref CI and real installed latency acceptance remain
required; no new production budget is claimed at this checkpoint.

## Activation and acceptance

Prepare a fresh exact candidate against current VERIFIED installed source, preserve
the existing Telegram owner/bot, voice model/cutoff and Google key/deployment binding.
Use a new source-bound Calendar config/profile, unchanged protected key, stock
prepare/inspect and encrypted backup/restore checks. Do not edit compose/runtime
limits directly or relabel an old image. No deployment follows from CI alone.

After exact finite-window installation approval: stock apply once; inspect actual
result on failure and use stock reconcile for a matching target. Previous operator
entry fix is included. Keep unchanged strict heartbeat readiness and existing bounded
operator wait if needed; never manufacture VERIFIED or owner resume.

Measure at least one isolated /help and one isolated Calendar query through real
owner Telegram with voice running, without queueing another test ahead of it.
Record UI send, server registration/read/delivery and Google transport separately.
Keep failures/duplicates/stop and all audit history checks. Confirm budget really
is1CPU, all five services run, memory/privileges remain unchanged and paid calls0.
If observed delays remain high, investigate audit/queue work using actual timings;
do not skip integrity checks or promise that this resource change resolves all latency.

Next overall phase2 result is the actual phone voice→transcript→confirm→saved task
acceptance. Calendar event writes, Google scope expansion and paid model use are not
part of this change and still need their concrete approvals when prepared.
