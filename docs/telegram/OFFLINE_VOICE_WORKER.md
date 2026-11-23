# Offline Russian voice intake

The owner asked to make voice intake usable without paid AI while Google Calendar
consent waits for their return. This change supplies the missing downloader and
real local speech decoder, composed with the existing transcript readback/receipt.
It does not activate a production worker or authorize execution of a saved request.

## Path

1. Existing owner/private-chat intake records a bounded voice note (120 seconds,
   5 MiB). The poller does not run speech inference.
2. A separate `command_center.voice_worker` process picks completed intake records
   from one exact connection/profile, no earlier than its explicit `since` cutoff.
3. Only Telegram `getFile` and the exact returned `voice/...` file are downloaded.
   File reference, unique ID, size and approved connection must match. Redirects,
   arbitrary hosts/paths and oversized replies are rejected. URL-bearing errors
   are redacted, not logged.
4. PyAV bounds decoded samples to 120 seconds/16 kHz/mono in memory. Local
   faster-whisper CPU/int8 inference uses a four-file hash-pinned model snapshot,
   Russian, VAD and no prior-text conditioning. No paid API or runtime model
   download is used. Empty/noise/oversized transcripts fail closed.
5. The existing transcript card presents the text. Only an observed owner click
   saves a request and offers the existing project picker. Duplicate callback
   update IDs cannot save another copy. This creates no F1 execution grant.

Google events, calendar voice (`/calendar` caption), goal classification, task
execution and replies spoken aloud are not implemented by this intake worker.
Project selection remains explicit; future owner-defined sections are not guessed.

## Activation contract

The optional `speech` dependency group is locked separately in
`requirements.speech.lock`. API/poller images do not install it. Docker target
`speech` adds the runtime and disables Hugging Face/Transformers online access.
The model weights are not committed: the exact official snapshot and SHA-256
manifest are in `deploy/speech-base-model.json`.

The POSIX worker accepts `inspect --config ABSOLUTE_PRIVATE_FILE` or
`run --config ABSOLUTE_PRIVATE_FILE --approved-profile EXACT_DIGEST`.
Configuration is read using the existing protected-file checks. Fields:

```json
{
  "enabled": false,
  "connection_file": "/run/secrets/telegram/connection.json",
  "connection_digest": "<64 hex digits>",
  "source_revision": "<40 hex digits>",
  "model_directory": "/models/whisper-base",
  "model_manifest": {"<each reviewed filename>": "<SHA-256>"},
  "since": "<explicit offset-aware activation time>"
}
```

`inspect` prints only a profile digest and non-secret flags; it does not read a bot
token, connect to Telegram or load a model. `run` requires enabled=true, the exact
profile digest, matching source and approved existing connection. It takes a
separate PostgreSQL advisory lock, checks ownership of that lock at each boundary,
and honors normal stop/recovery/epoch changes and profile revocation. Inference
has a 90-second POSIX deadline. Failure queues one bounded human-readable reply;
it does not loop forever or persist audio bytes. A crash before proposal can safely
re-read the same file; an existing proposal is not downloaded/inferred again.

Production needs a reviewed release/prepare/inspect/install/postcheck integration
for this additional service and explicit resource headroom. Use a separate
unprivileged constrained container with read-only source/model, bounded temporary
storage, one CPU, measured memory/pid limits, no Docker socket or executor/publisher
credentials, existing application DB and exact Telegram credentials only. Do not
add it to a running VPS with an ad hoc compose command. The current existing VPS
installer does not yet activate this additional service.

## Evidence and limits

A genuine local CPU inference on Windows recognized a 4.214-second synthetic
Russian recording as `Завтра в 15 часов позвонить поставщику.` in 7.88 seconds,
including model initialization (not the one-time model download). No owner audio
or paid service was used. This is not a VPS latency or recognition-quality claim.
Deterministic transport/worker tests use synthetic audio/text and MockTransport;
they are not genuine Telegram end-to-end acceptance. See the dated handoff for
final tests/CI and outstanding release prerequisites.
