# Russian ASR candidate — phase2/6

Installed runtime remains42b8238/PR116. This branch prepares an optional, pinned
offline GigaAM v3 E2E CTC int8 decoder; no server installation, paid call, new
permission, Calendar write or merge is performed by this work.

Final reviewed application source1e5dd99f03b2e7bcb17f29164994b2d136118057,
PR117 Draft. CI45621267384 and45621267808 SUCCESS; merge-ref
8f689139d969b04332527fe97ea6903af1d4f920 has identical tree
fae5bdac962a4b4986d0e63fd593ecadf15da553. Main suite2742 passed/1 skipped/
1 dependency deprecation warning; separate infrastructure1014 passed, separate
speech44 passed with source-pinned image import smoke. Suites overlap and are
not summed. This documentation checkpoint is not a new installed app revision.

## Measured candidate

Primary sources: [original model](https://huggingface.co/ai-sage/GigaAM-v3),
[ONNX conversion](https://huggingface.co/istupakov/gigaam-v3-onnx),
[library](https://github.com/istupakov/onnx-asr).
The ONNX snapshot revision is322c3b29492673eb7d0b434bfa9dfb8653e34d02;
four exact files and their SHA-256 pins are in deploy/speech-gigaam-model.json
and speech_models.GIGAAM_MANIFEST. LFS weight hash and small-file Git blob hashes
were independently checked at download. MIT license/attribution file is retained.
Model download was preparation only; no runtime download or remote model code.

Actual worker decoder tested locally on two owner phone recordings, their
seeded additive-white-noise10dB copies and four clean synthetic utterances.
The original first voice was already in protected PC custody; the second was
retrieved through the existing bounded Telegram file downloader after read-only
binding to its source fingerprint, raw proposal audio hash and accepted family.
No second poller or fabricated incoming owner update. Audio, references and
detailed transcripts remain in owner-only PC custody, outside Git.

On this Windows PC/one CPU thread, actual GigaamSpeech decoded the four real/noisy
clips in1.70–1.90s, peak working set364.3MiB across eight cases, model load about1s.
All operator-labelled key phrases survived both original and noisy copies. The
second voice's inflection error was corrected by ASR; filler sounds/punctuation
remain imperfect. Whole real references are operator assembled, not a full
independently owner-approved transcript, so do not advertise zero overall WER.
Earlier Whisper Base times were around5s and Small20s; runs were not a repeated,
isolated CPU benchmark. No VPS Linux speed/accuracy acceptance is claimed.

[Metadata-only evidence](../jarvis-2/evidence/russian-asr-20261125.json).
Python socket connections were denied during inference, ONNX telemetry disabled,
and the child inherited no API credentials. This is not an OS network namespace
or proof that a Windows memory reading equals Linux cgroup charge.

## Resource and text bounds

Whole120s inference failed under a Windows1GiB private-commit process limit:
attention attempted one576MB allocation. It must not be deployed in that form.
The implemented decoder uses existing pinned Silero VAD only to find chunk
boundaries, with15s maximum windows, preferably at pauses. Chunk ranges cover
every input sample exactly once, without overlap or word deduplication. Fully
silent ranges are not inferred; a speech-containing range with empty output
fails instead of silently dropping that range. Hard boundaries remain possible
when no pause exists: owner readback is still mandatory.

Synthetic repetition stress using actual GigaamSpeech, Windows1GiB cap:
30s →10.073s/363.2MiB, successful contract;120s →39.751s/414.4MiB,
safe expected rejection at the existing2000-byte output bound. No OOM/no text
truncation. Earlier chunk-only experiment covered all samples in9 chunks with
no hard cuts,40.319s/390.8MiB, but produced2008bytes and was NOT an accepted
worker result. This is a resource test, not real long-form semantic acceptance.
No limit expansion in this change: very long transcripts still fail clearly.

A further positive120s public synthetic repetition with pauses passed the actual
decoder contract:39.754s,395.0MiB peak,1322-byte output, Windows1GiB private-commit
cap, no paid calls. Thus120s input is not categorically rejected: output size
still determines acceptance. This is a synthetic resource result, not120s live
phone/road-speech acceptance. Fixture/metadata are in ignored local release kit.

Two more copies of the real phone clips used seeded colored noise plus90/180Hz
hum at5dB SNR, not real road recordings. Key phrases remained intact. Four
additional Microsoft Irina synthetic cases preserved labelled names, address,
date/time and negation; textual numbers were normalized correctly in these
examples (including50 vs15), and an unspecified time was not invented. Complete
references/reviews stay in private custody; results are limited cases, not a
general safety guarantee or automatic Calendar permission.

## Existing release interlocks

Profile schema and legacy serialization are unchanged. Exact file keys identify
the backend within the already-approved profile/model digest. Legacy four-file
Whisper snapshots keep the same path and decoder. GigaAM accepts only the one
reviewed snapshot above; unknown/mixed/modified formats fail closed.

The existing assistant prepare/inspect operator gains optional explicit
--model-directory and --model-manifest-file for this fixed snapshot. The latter
contains just the files map. Source, candidate, preparation and image pins still
apply. Only the model path/manifest may change; owner, connection, cutoff,
enabled flag and all other profile fields must be preserved. Exact model bytes,
custody, read-only mounts,1CPU/1GiB/pids64, network/secret boundaries and heartbeat
fingerprint checks remain enforced. No independent grants mechanism or new service.
Omitting replacement flags preserves the currently installed model.

Speech dependency group adds onnx-asr0.12.0, fully locked/hashed. Main app
dependencies are unchanged. The optional speech CI job includes the new decoder
and partition tests. No voice processing is moved into the Telegram poller.

## Validation and remaining activation

Local focused suite46 PASS; Ruff PASS; Bandit medium/high PASS; locked speech
dependency audit found no known vulnerabilities. Linux/PostgreSQL release
interlock tests require final CI (local Docker daemon remains unavailable).
Check final HEAD/merge-ref, not the predecessor's CI. Real phone data is not
uploaded to CI. Synthetic/mocked tests are not ASR accuracy or VPS acceptance.

Local release kit `.runtime/russian-asr-release-1e5dd99` contains the source
bundle, verified four-file model tar, bare model manifest and public synthetic
120s fixture. Source bundle SHA-256
a4e8462356b972d00545c5659cea5531cea658fe5dff0efdb01f7b10f83ab2a6.
Model manifest digest515e892df96c91b5bcd6234d61655836c1891585fcb8d3966d96b9e3462428b6.
No server images/model/profile have been staged by this turn. The earlier PR116
permission expired12:10:04UTC and does not authorize this model/source deployment.

Fresh read-only server check13:29:25UTC: exact42b8238, deployment/activation
VERIFIED, OPEN epoch62/recovery=false, fresh Telegram/voice IDLE heartbeat,
actual4 historical units/reserved0/uncertain0. Backup directory252742038bytes
of268435456byte quota; latest backup4873926bytes. About15.7MB remains, so fresh
size/capacity checks are required before every backup. No cleanup/quota bypass
authorized or performed. Available disk about30.8GB. Do not confuse disk space
with the independent backup quota.

After successful CI: bounded owner approval for the exact source/model, fresh
read-only VPS reconciliation and backup-capacity check, exact rootless images,
private model snapshot, network-none Linux resource smoke under1CPU/1GiB,
verified independent backup, stock prepare/inspect/install/postcheck and actual
Telegram voice/readback/save acceptance. Retain the old model/profile/images;
do not relabel old images or infer deployment permission from local evaluation.
No deployment approval requested before that tested source is concrete.
