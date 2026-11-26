# Combined voice/MVP acceptance — incomplete, bounded repair prepared

Owner requested combined long voice, correction, task/idea/reminder and Calendar
verification after installed PR124. Verified application/sourcec25e2d3; final
CI45815091382 SUCCESS rechecked. Base remains unmerged PR124; no merge, new
production deployment, paid call, model change or new Calendar event authorized
by this test stage. Current production source has not been replaced.

## Observed gaps, not a passed mixed-message workflow

Existing personal parser turns explicit task + separate idea + reminder into ONE
task title containing all text, no distinct idea/reminder and no definite project.
This was reproduced on the91word public reference and actual deployed-ASR output.
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
Two new PostgreSQL acceptance cases await final CI: mixed text leaves no domain
effects; voice raw/correction/stale card/current approval -> held source -> separate
personal task and idea with correct projects/no invented deadline -> completion ->
precise reminder once after restart -> separate meeting missing-time dialogue ->
explicit observed confirmation -> one MOCK Calendar write. Provider/UI protocols
in this test are mocks; no actual voice receipt or real Google insertion claimed.
Local Linux Docker unavailable. Final source/PR/merge pins and CI pending.

Real phone long-voice accuracy and full one-message multi-item assistant acceptance
remain open. Stage2 is NOT complete. New guard deployment needs a separate exact
release approval; this check does not authorize provider expenses or model changes.
