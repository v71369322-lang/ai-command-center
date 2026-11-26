# Internal undated project planner — bounded development slice

Owner clarified that Jarvis must keep its own undated plans/ideas by project,
distinct from timed Google events, and authorized continued development. Local
base72775db on codex/personal-inbox-release-review retains PR120 and its verified
e238589 application dependency. PR120 CI45768463214 SUCCESS rechecked at entry.
No server access, deployment, deletion, paid AI or new external connection in
this slice. Last installed release remains the previously verified PR119/b808144;
old reports are not a current server-health assertion.

## Result

- «Планирую проверить вентиляцию в кондитерской», «Я планирую обсудить закупки»
  and «На потом: разобрать документы» save a deferred personal task WITHOUT a
  deadline. Existing source/audit/status/project classifier/outbox are reused.
- «Мои планы», «Что без срока», «Напомни, что я планировал» retrieve open undated
  tasks; «Что отложено» retrieves deferred tasks. These are read requests, not
  new scheduled notifications or copies of old plans.
- «Что отложено по кондитерской», «Планы по ванилисахару», «Идеи по автосервису»
  select the existing project and correct kind/status. Unknown project returns a
  clear refusal instead of displaying another project's items. Completed tasks
  stay out of open overviews; ideas stay distinct from task obligations.
- Query filters use CURRENT existing project assignment so later classification
  corrections are reflected. Source text/history remain untouched. Recreating
  the configured polling service reads the same stored plans.
- Daily local reminder filtering now converts the stored instant into the
  current owner timezone before comparing dates, including midnight boundaries.

No new database tables, services, project registry, AI model or reminder daemon.
Existing bounded lists/capacities remain. This is internal persistent planning
data, not a second Google Calendar or autonomous scheduling authority.
The planner shows the last12 matching open records; task deadlines are never
invented. Mixed long speech splitting, semantic search and general memory of
decisions remain outside this slice. Existing owner voice confirmation is kept.

## Proactive review policy

Review is ON REQUEST for now. A plan without deadline does not acquire a hidden
reminder date. Existing explicit timed reminders from PR120 remain available.
Daily/weekly resurfacing needs an agreed cadence, time, quiet hours and delivery
acceptance before activation; no recurring schedule was inferred or enabled.
This preserves the owner's time and avoids unsolicited notification noise.

## Checks and release boundary

Pure parser/filter/date tests cover exact natural queries, project separation,
deferred/no-date state and timezone boundary. PostgreSQL tests cover persisted
project overviews, completion exclusion, unchanged F1 authority and zero reminder
creation; configured HTTP polling tests reload the same plans from the store.
Local Docker remains unavailable; final CI required before release. Synthetic
HTTP/PG tests are not live Telegram/VPS or phone voice acceptance.

This extends unmerged PR120; a future approved exact release must include both
dependencies. No merge/retarget of existing PRs. Stage2/6 remains incomplete:
prepare final verified source, get exact deployment/backup retention approval,
then test real owner voice/text, project recall, completion and one timed reminder.
Backup quota and retention are governed by the last live handoff and fresh VPS
reconciliation, not an implied authorization from this development request.

Final source75776b039b732698e83cc77c2da051e75123ec9a / Draft PR121:
CI45776306557 SUCCESS, main2857passed/1skipped/1warning, infra1014passed,
speech44passed. Merge-ref7796efed54e61de1651cc6e6b6bc59479634e260 verified.
[Consolidated exact release and retention proposal](JARVIS_UNDATED_RELEASE_2026-11-26.md).
Still not installed; no VPS access in this development stage.
