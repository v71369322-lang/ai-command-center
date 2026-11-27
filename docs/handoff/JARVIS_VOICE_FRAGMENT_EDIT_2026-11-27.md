# Owner-requested literal fragment correction

Owner requested continuation after real82s voice review. Clarified migration
wording; meeting was ONLY a test and must not be scheduled. Site spelling remains
ambiguous, no inferred correction. No live voice acceptance/correction/scheduling
performed by this development slice; original proposal remains unaccepted.

Existing owner Reply correction required resending the entire transcript. Add
bounded literal replacement on the same observed Reply path:
Замени «старый фрагмент» на «новый».
Straight double quotes and curly double quotes also accepted. Exact case-sensitive
fragment must occur once, including overlapping occurrences; no fuzzy matching,
inferred spelling, regex replacement, multiple instructions or word normalization.
Malformed/missing/repeated fragment refuses with a useful receipt. Reserved prefix
Замени begins this bounded grammar; ordinary full-text replies and /stop remain
data. Result must satisfy existing2000UTF8 byte/secret guard; oversize result gets
refusal rather than an uncaught poller failure. No automatic save or scheduling.

Reuse the existing CORRECTED event and one-save family, observed-card binding,
owner incoming fingerprint/anchor, source/audio/epoch/revision checks. Partial
correction records edit_mode=replace_once and previous_text_hash; acceptance
reconstructs the exact requested replacement from the anchored owner instruction
and observed predecessor delivery. Original ASR remains unchanged. Older full-text
correction events without edit_mode retain their existing equality validation;
full and fragment edits can be combined. No second permissions mechanism.

Public synthetic tests only; no private owner transcript/audio in fixtures.
Local16 unit cases PASS;7 new PostgreSQL cases and final CI pending. Full Linux
container/DB unavailable locally. Static/contract checks pass. No mock is live
Telegram/phone acceptance. This improves correction usability, not acoustic ASR
or punctuation quality. No model/API/Google change, paid call, VPS access, merge,
deployment, cleanup, quota increase or new external integration. Stage2 incomplete.
Base is unmerged PR127/codex/voice-quality-corpus at4f51e27, preserving docs chain.
