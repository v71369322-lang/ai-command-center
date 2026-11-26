# Local ASR comparison and evaluation corrections

Owner requested continued development after PR126 installation. Local work only:
no VPS access, deployment, merge, paid call, model download/activation or new
external data transfer. Production last verified73647d0 in its dated handoff.
Preserve the unmerged PR126 chain; new branchcodex/voice-quality-corpus.

Existing local exact pinned GigaAM and Whisper Small snapshots were verified before
inference, CPU1/int8/fresh sequential processes. Same Windows workstation, not VPS
performance and not a strict exclusive-CPU benchmark. Four existing public short
synthetic clips plus the63.876s public long fixture were compared. Added47.725s
held-out synthetic date/name/negation text and a deterministic white-noise15dB
variant; this is NOT real roadside/owner phone acceptance. Public references and
audio hashes:tests/fixtures/asr_quality_corpus_public.json. WAVs and raw reviews
remain local under.runtime/voice-quality-next, no private owner content committed.

Current GigaAM error "не переноси" -> "на переноси" reproduced locally. Longest-
pause chunk prototype did not repair it and increased long-sample lexical edits
4->5; rejected, no runtime/chunk change. Whisper Small/beam1 preserved the labelled
critical phrases on the initial five clips and long-sample edits4->2, but took
59.304s versus GigaAM22.612s on THIS Windows host; memory729.0 vs388.4MiB. On the
new noisy holdout it omitted an entire name/meeting clause (15/63word edits,
three missing critical labels), so this is not evidence for a safe model switch.
Additional bounded decoder experiments and final assessment recorded below.

Evaluation bugs corrected without changing ASR or action authority: one preserved
instance of a repeated critical phrase could hide another dropped instance. Count
all reference/transcript occurrences, retain missing indexes for shortfalls, report
extra/missing-count indexes. Punctuation previously compared only symbol order;
commas in the wrong word positions could appear equal. Add literal word-boundary
punctuation comparison, retain the old sequence metric and mark report schema2.
Counts do not prove correct context/date equivalence, and boundary equality is not
grammatical quality. Human review always required; no result grants action rights.

Local19 evaluation/CLI tests PASS, including7 new regressions. Scope static and final
CI pending. No inference/model comparison is claimed as CI or live acceptance.
Model/profile unchanged; Stage2 remains incomplete.
