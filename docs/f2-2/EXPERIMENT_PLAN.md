# F2.2 first experiment — preparation only

Source: owner's F2.2 instruction, preliminary ceiling **100 RUB total**, not payment
authority. Base PR #14: `fb1ed9e810e4850ec56740c5f9cfc69e1625dfb5`.
No VPS/CRM/customer data, real credential, paid call, new publisher write,
account/resource creation, deployment or merge is authorized in this preparation.

## Scope and official facts (observed 2026-10-24)

One owner, one synthetic repository, one fixed F2 Git base, one task/executor,
up to two Responses requests (one initial edit + at most one repair), separate
verification and draft PR only. A correct first response needs no paid repair.
Task: `sum_positive_v1`, editable file `calculator.py`; acceptance tests and
README remain immutable. Existing F1/F2/F2.1 orchestration is reused.

Candidate exact snapshot: **gpt-5.4-mini-2026-03-17**. Official catalogue documents
Responses, structured outputs, coding use and 400,000 context tokens. Standard
text prices: **$0.75 input / $4.50 output per million tokens**, cached input
$0.075; caching discounts are ignored in our bound. We cap output at 2,048
tokens/call and explicitly request `service_tier=default`. Tools, hosted shell,
search, files, images, regional/FedRAMP endpoints and Fast processing are absent.
Reasoning output, if present, is included in the output-token allowance.

Sources:
- <https://developers.openai.com/api/docs/models/gpt-5.4-mini>
- <https://developers.openai.com/api/docs/pricing>
- Official request schema: <https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_create_params.py>

This proves public documentation, **not access for the owner's account, region,
billing tier or credentials**. Older GPT-4.1 Mini / GPT-5 Mini catalogue pages
were marked deprecated when checked, so they were not selected.

## Conservative arithmetic, not a provider-enforced RUB cap

Reserve the entire documented input context each time, despite the much smaller
bounded exercise prompt. Standard-price upper calculation:

`2 × (400000 × $0.75 / 1000000 + 2048 × $4.50 / 1000000) = $0.618432`.

CBR reference **1 USD = 80.5381 RUB**, effective **2026-10-24**:
<https://www.cbr.ru/currency_base/daily/?UniDbQuery.Posted=True&UniDbQuery.To=24.10.2026>.
Reference result: **49.8073382592 RUB** (display 49.81 RUB). Nano-RUB reservation
rounds upward. A planning 50% margin would be 74.7110073888 RUB, but that margin
is **not** evidence of bank FX, tax or fees and cannot unlock payment.

Live activation requires an independently evidenced all-in upper conversion rate
and extra-charge bound. Code verifies `0.618432 × FX_upper + extra_upper ≤ 100`
and that the actual tariff reservation, including integer rounding/fixed extras,
also fits 100 RUB for both calls. At zero extras the mathematical FX threshold
is approximately 161.699265 RUB/USD; this is a threshold, not a quoted rate.
Unknown fees or an unbounded conversion rate keep the experiment blocked.

OpenAI billing controls are separate: the current projects guide describes an
optional enforced spend limit with non-instantaneous enforcement; alerts alone
do not stop calls. Prepaid balance also is not an instantaneous cutoff.
Sources:
- <https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform>
- <https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing>

Minimum new prepaid purchase is **$5**, about **402.6905 RUB** at the reference
rate, already above 100 RUB. No purchase is performed. A usable pre-existing
balance sufficient for the bound must be confirmed; otherwise stop and obtain
a separate funding decision. Disable auto-recharge for the isolated project
after separately authorized setup; do not claim this prevents delayed charges.
Never treat internal reservations as a guaranteed provider-side spending cutoff.

## Enforced preparation/live boundary

`FirstExperiment` narrows F2.1 configuration; no new scheduler/permission system.
Nine preconditions plus exact final owner approval cover: account model access,
current price, payment bound, protected OpenAI credential, GitHub App rights,
repository ID/baseline/protection, runtime, dry-run and existing funding.
Evidence expires; task/model/source/config changes invalidate permission.

Current defaults: live disabled, no evidence, no numeric repository ID, no payment
terms, no credentials, no final consent. Public facts and a 100 RUB ceiling do
not turn any gate on. The preparation API creates only a waiting task; repeated
phone taps return that same task. The API's separately typed final confirmation,
or the [explicit observed private-owner Telegram card](../telegram/EXPERIMENT_AUTHORIZATION.md),
binds the current profile hash, task version and financial scope through the same
F1 authorize path. Preparing or requesting that card is not consent. The generic F2.1 approval endpoint
cannot substitute for it in live experiment mode.

Only one task can receive the experiment grant in each mode, atomically under
the F1 PG lock. HTTP-mock grants cannot be promoted to live: mode/config hashes
and final approval differ. Daily/monthly/task room is capped at 100 RUB, at most
two AI calls, no automatic repeat after ambiguity. Unknown money stays reserved.
Numeric repository ID and protected exact main SHA are freshly checked **before
the first AI request** and again before publication. No force update/merge exists.

## Credentials, repository and account setup — future permission required

Proposed name only: `v71369322-lang/acc-f2-synthetic-first`. **Not created or
checked for existence in this stage.** ID/installation credentials remain absent.
Create it only after explicit account-change permission. A public synthetic-only
repo can avoid paid branch-protection requirements; no real or private data goes
there. If the chosen account cannot provide required controls for free, stop.

Future cloud-only setup sequence (the owner needs no PC or local commands):
1. After permission, create an empty synthetic repository with no auto README,
   record authoritative numeric repository ID, and verify owner/name.
2. In the approved cloud workspace run the **offline** generator:
   `.venv/bin/python -m command_center.coding.seed .runtime/f22-seed`.
   Verify `main` SHA `a41d5fdf083fa0a162299b74ac9c155b58b140cb` and the three files.
   The generator has no remotes or network actions and refuses an existing path.
3. Only with separate write permission, trusted cloud setup pushes that exact
   `main` to the approved numeric-ID repository. Never use CRM or Command Center
   write credentials in the coding sandbox. This initial seed is setup, not an
   agent publication or merge; it is not performed during preparation.
4. Protect main: PR/review required, no force push/deletion, no App bypass. Owner
   verifies rules; the publisher only creates new `f2/task-*` branches and drafts.
5. Create/install a GitHub App for **selected repository only**; Contents write,
   Pull requests write, implicit Metadata read. No administration, Actions,
   organization-wide or unrelated repo access. Verify installation ID, selected
   numeric repo ID and token permission evidence before consent. These rights
   do not themselves prevent merge; gateway endpoint policy and branch rules do.
6. Inject a short-lived installation token and a restricted project OpenAI key
   through the platform's protected credential bindings into the trusted gateway
   only. Mode 0600, no symlinks, no chat/browser/Git/prompt/log/artifact values.
   No keys in executor/worker. Record revocation/rotation procedure. Do not paste
   an OpenAI key into this chat; if protected injection is unavailable, stop.
7. After separate read-only access permission, verify exact model availability,
   remaining balance, applicable tariff, payment FX/taxes and runtime. Mount
   versioned operator config as in F2.1; attach expiring evidence to the same
   repository/model/profile. Refresh the dated public reference before live use.
8. Review successful dry-run evidence, then obtain **one final exact bounded
   owner approval**. No ordinary file/test/repair steps need separate consent.

Revoke the OpenAI project key and GitHub installation access if unsafe activity
is suspected; preserve journal/checkpoints and cancel through F1. An unknown
response/PR outcome stays blocked pending reconciliation; no blind retry or
automatic authority renewal. All real account changes above remain unperformed.
