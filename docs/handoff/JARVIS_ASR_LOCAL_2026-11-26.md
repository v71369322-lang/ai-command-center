# Local ASR comparison and evaluation corrections

## Confirmed runtime reminder bug and limited fix

While examining actual Small transcript wording, reproduced:
"Напомни послезавтра в 9 часов 15 минут позвонить Анне" parsed as09:00,
with "часов 15 минут" incorrectly included in the title. No such wrong reminder
was sent to production during this check. Explicit numeric hour/minute units now
parse09:15 with clean title, preserving raw intake/ASR. Whole-hour unit forms and
existing colon clocks remain; recognized unconsumed minute/second/AM-PM/half-hour
suffixes refuse rather than invent a whole hour. This is bounded grammar, not a
general natural-language clock parser. Russian number-word minutes/day periods
remain unsupported and request an explicit clock; no date/time guessed.

25 new local clock regressions plus3 PostgreSQL cases: owner-reviewed mixed span
is not queued at09:00 and queues at09:15; approved raw voice preserves09:15 or
refuses invalid75minute suffix. Actual ASR is not invoked by these integration
fixtures. Original receipt date/zone, review source/revision/epoch, duplicate and
permission boundaries preserved. Google event parser unchanged, no new authority.

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

Local58 selected clock/evaluation/CLI tests PASS (overlap with future full CI),
including7 evaluation and25 clock regressions;3 new PostgreSQL cases pending
final CI. Ruff, scope static, contract and diff checks PASS. Final application
HEAD/merge-ref CI pending. No inference/model comparison is claimed as CI or live acceptance.
Model/profile unchanged; Stage2 remains incomplete.

## Additional measurements and prepared external probe

Small/beam5 on the fresh clean/noisy47.725s holdout retained every labelled
critical phrase; noisy lexical edits3/63 versus Small/beam1 15/63 with a clause
omitted. On120s concatenated/padded public stress audio, GigaAM5/154edits but one
of two "не переноси" occurrences lost; schema2 correctly catches this despite
another surviving occurrence. Small/beam5 7/154edits, all labelled counts preserved,
107.172s inference and729.4MiB peak on Windows. Exceeds current90s request budget
HERE: no activation justified and no VPS timing extrapolated. Punctuation still
differs, numbers/words affect lexical edits, critical labels are not all semantic
entities. No real owner/roadside quality PASS.

Prepared local exact source73647d0 speech-image/public8case payload and rootless
VPS comparison plan under.runtime/voice-quality-next. Controller/payload syntax
and Ruff checked; NOT run on VPS and requires fresh separate exact permission.
Fixed source/image, source journals/manifest, pinned existing GigaAM and Small
fingerprint40f0d23210624a91a050b5f38dc16e7957211c5f44439babd9cdcef5b1eff3bb;
Small originSystran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120,
model.bin SHA3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671
verified against the author's pinned public repository. At most600MiB public
model download, two disposable containers each CPU1/1GiB/64PID/read-only/no-network/
no capabilities/no credentials/tmpfs32MiB,600s each; host reserves2GiB RAM/disk.
Exact labelled-container cleanup after inspection, no production stop/restart,
config/profile change, Google/Telegram send or paid API. No automatic model switch.
Current deployed worker is beam1 and candidate transition admits only the existing
exact GigaAM swap: Small/beam5 is an experiment, NOT a ready runtime profile.
If a new app release changes source/image, this prepared probe must be re-prepared
and approved against the new actual runtime; never bypass the exact preconditions.

Source verification: https://huggingface.co/Systran/faster-whisper-small/blob/536b0662742c02347bc0e980a01041f333bce120/model.bin
