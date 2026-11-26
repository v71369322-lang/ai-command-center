# Combined voice/MVP acceptance — incomplete, bounded repair prepared

Owner requested combined long voice, correction, task/idea/reminder and Calendar
verification after installed PR124. Verified application/sourcec25e2d3; final
CI45815091382 SUCCESS rechecked. Base remains unmerged PR124; no merge, new
production deployment, paid call, model change or new Calendar event authorized
by this test stage. Current production source has not been replaced.

## Observed gaps, not a passed mixed-message workflow

Existing personal parser attempts ONE task title for explicit task + separate
idea + reminder, without distinct idea/reminder or definite project. Reproduced
on the91word public reference and actual deployed-ASR output; resulting titles
are619/605 characters and exceed the existing500-character validation limit.
Thus this long sample would be rejected, not saved as one task. Shorter mixed
messages can instead collapse into one title.
No such mixed record was accepted into real personal tasks during this check.

Public63.876second Microsoft Irina Desktop synthetic speech, WAV2816978bytes,
SHA256a500f032b20fae540f99972510c71d82b48ca1dcdfd79ccb7ae01d0b03b36dfa.
Same exact deployed speech imagef223d4178b76aad7774a8b4cf8bc4ee11e715d06674343a7b8613f1c95a59845,
GigaAM fingerprint515e892df96c91b5bcd6234d61655836c1891585fcb8d3966d96b9e3462428b6.
Bounded separate1GiB/1CPU/64PID read-only/no-network/no-credentials container;
existing model mounted read-only, host free-memory guard, test container removed.
Load0.850s, decode+inference3.803s, peakRSS558.79MiB, exit0/noOOM. Primary services
not stopped or changed. These are offline decoder measurements, not Telegram
latency or a real owner/noisy-road recording. No new model downloaded.

Punctuation present but critical negation failed: reference "не переноси" became
"на переноси". Existing lexical evaluator:4 edits/91 words,4.396% WER, missing
critical index0 of6 labelled phrases. Digits/words and morphology contribute to
lexical edits; manually verified dangerous negation error must not be hidden by
low WER. No silent grammar/negation correction or quality PASS. Original ASR and
owner corrections remain separate. Public reference/transcript retained in
`tests/fixtures/mvp_long_voice_public.json`; no owner audio/text published.

## Limited repair, not automatic batch understanding

New shared mixed_inbox ingress holds clearly explicit multiple creation markers
BEFORE personal and Calendar routing, for text and owner-accepted/corrected voice.
Keeps SAME immutable Inbox source and all original wording; NEEDS_PLANNING and
one audit/receipt. No fabricated owner updates, child tasks, dates, project choice,
reminder, Calendar draft/write or grants. Duplicate update/current voice-card
boundaries remain. Receipt explicitly says separate actions have not been created
and asks for one item at a time. Quoted examples/negated creation markers excluded.
Detection is bounded phrase recognition with possible false positives/negatives;
not general NLP, automatic decomposition or an ASR accuracy fix.

15 local detector/public-regression cases and Ruff/Bandit/contract/diff PASS.
Two new PostgreSQL acceptance cases passed final CI: mixed text leaves no domain
effects; voice raw/correction/stale card/current approval -> held source -> separate
personal task and idea with correct projects/no invented deadline -> completion ->
precise reminder once after restart -> separate meeting missing-time dialogue ->
explicit observed confirmation -> one MOCK Calendar write. Provider/UI protocols
in this test are mocks; no actual voice receipt or real Google insertion claimed.
Local Linux Docker unavailable; PostgreSQL/container evidence comes from CI.

Real phone long-voice accuracy and full one-message multi-item assistant acceptance
remain open. Stage2 is NOT complete. New guard deployment needs a separate exact
release approval; this check does not authorize provider expenses or model changes.

## Final source and CI

Draft PR125: https://github.com/v71369322-lang/ai-command-center/pull/125
Source bb944ff863b7af39c8dbca29182280140780cb3f; base PR124 branch
codex/attachment-retrieval at c25e2d30ec49bad7347cf3274714bbb520cffd3d.
Merge-ref6f9d25361a526a15147611fb752246c56b5742ec; head/merge tree
 a3968b52b712a3de237dc2552351c0f7d53f7481 (identical).
Final CI45826953730 SUCCESS: synthetic2926passed/1skipped/1warning,
infrastructure1014passed; speech job139933456509 SUCCESS. Encrypted backup to
separate networkless PostgreSQL restore, audit and binary fixture PASS.17 new
cases total (15 local,2 PostgreSQL); overlapping suites/runs are not summed.
PR remains Draft, unmerged and NOT INSTALLED. This documentation checkpoint does
not change the tested application source.

## Real individual Telegram checks,26 November

Actual owner web chat: public task131179298 saved, explicitly assigned to
vanilla-sugar, completed without deadline. Public idea131179299 assigned lnauto;
completion correctly refused for an idea, then source reversibly ARCHIVED and
verified absent from active idea list. Initial project ambiguity was caused by
both the test word Jarvis and another project; no silent assignment was forced.
Public reminder131179300 due16:24Moscow: exactly one queue entry13:24:00.309965UTC,
SENT receipt389, visible Telegram message16:24:02; then completed. Each source
created exactly one personal record, no F1 task. Existing owner records untouched.
Read-only Google agenda returned the existing27November15:00 event; no new Google
write. Agenda took19s including queue wait, not instant Calendar responsiveness.
Final read-only metadata receipt13:26:21UTC: control OPENepoch85,
historical actual4/reserved0/uncertain0. Health13:30:40UTC: all five service/model/
Calendar boundaries PASS; Telegram/voice heartbeats IDLE. No new production restart
was performed in this slice. Fresh-client DB evidence is not restart acceptance.
Private local receipts: .runtime/mvp-voice-check/result.json and personal-live.json.

## Existing local Whisper comparison, not a model switch

Same public WAV, existing pinned Whisper Small, int8/CPU1/beam5, local-files-only,
Windows faster-whisper1.2.1/ctranslate2 4.9.1. Fingerprint
40f0d23210624a91a050b5f38dc16e7957211c5f44439babd9cdcef5b1eff3bb.
Load2.167s, decode/inference73.51s, peak729MiB;3edits/91words (3.297%), no missing
critical labelled phrases. In particular "не переноси" preserved; punctuation
sequence still differs and human review remains required. This is one synthetic
sample on different hardware/platform from VPS GigaAM, not a strict speed/RAM A/B
or real owner/noisy-road acceptance. No download, paid call, model activation or
server change. Do not silently postprocess negations or switch based on one sample.

## Remaining acceptance boundary

Individual text task/idea/reminder and Calendar read were actually exercised.
Long voice -> multiple independently correct items remains NOT accepted. PR125
only safely holds explicit mixed instructions; it does not implement automatic
splitting. Real owner long/noisy recordings and date/name/negation review remain
necessary before claiming driving-quality capture. No new server release is
covered by this verification stage. No irreversible cleanup was performed.
