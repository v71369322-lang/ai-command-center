# PR128 — подготовленный выпуск и план ротации

**К согласованию: удалить только четыре перечисленные старые серверные копии,
затем установить PR128/sourcec837c2e через штатные проверки. Пока не выполнено.**

Эти четыре файла полностью сохранены на защищённом компьютере. Проверены
совпадение зашифрованных файлов, расшифровка, контрольная сумма данных и полное
восстановление с журналом аудита в отдельных изолированных базах. На сервере
сохраняется более новая копия каждой затронутой версии; все копии текущей и
предыдущей рабочей версии, latest.json и остальные файлы остаются.

| Только предлагаемые к удалению файлы | Создано UTC | Байт |
| --- | --- | ---: |
| `backup_a4ce53782f764695a072fb2268728e74.enc` | 2026-11-26 05:29:49 | 5355092 |
| `backup_47c0cd0dc484496c88206dc20c6b691e.enc` | 2026-11-26 05:35:06 | 5363452 |
| `backup_b0f4751f83a547ee859b918e02a79a47.enc` | 2026-11-26 08:19:20 | 5442062 |
| `backup_89cd52f6d367421882ce63ff0833cd62.enc` | 2026-11-26 10:48:20 | 5518528 |

Освободится21679134байта (около21,7МБ). Свободный остаток лимита копий вырастет
с10889021 до32568155байт. Никакая копия ещё не удалена. Лимит не повышается.
[Точные хеши, список сохраняемых версий и план восстановления](../jarvis-2/evidence/PR128_RETENTION_PROPOSAL_2026-11-27.json).

## Разрешённая и выполненная подготовка

27November2026 owner approved SERVER PREPARATION ONLY after the concrete question
about backup reconciliation and package preparation for PR128/c837c2e.
New bounded window19:06:18–20:06:18UTC; not installation/retention approval and
not renewal of an earlier window. No stop/restart/activation/reconcile/install,
merge, file removal, quota change, paid API, model change/download, Google write,
Telegram send, access expansion or other project/CRM206.223.246.79 changes.
Owner's meeting sample is test-only: do not schedule it.

Fresh Git origin/fetch/main verified:mainf5ff8b2757b1b759b08a173fdac9d3e51f84d227.
PR128 still Draft/unmerged, base PR127/codex/voice-quality-corpus4f51e27.
Applicationc837c2e54961b72989fe47bf5505f32b01d8bb0e;
merge935774e64fd565563bfd3c604e2ed52492b99c0c;
identical treeaf16641ad686b0441543da460e916e1994696f44.
Final CI46049662208 SUCCESS rechecked:3024passed/1skipped/1warning,
infra1014passed/speech44passed; overlapping suites not summed. No code edits,
new CI, worktree, merge or retarget in this preparation stage.

Initial19:05:37UTC read-only reconciliation: live4f51e27, both deployment and
activation VERIFIED, exact five-service/model/Calendar custody PASS; OPENepoch97,
historicalactual4/reserved0/uncertain0. Backup257546435/268435456bytes, disk
21820854272bytes free. Some historical Telegram network failures had consecutive1;
no repair or restart performed as part of this preparation.

## Exact package

Private root /home/acc-control/jarvis-fragment-c837c2e-release.
Source bundle SHA d0f00fd2d15594217423cd0bdce42504df01b63a8137f6ab343ebf5c7f2072ac.
Previous bundleea3ca20867b99356ff5765802e7f69c04d2841a77f4710c7c8e8ca5867eaba49.
Candidateb0c5037f2450764648dd96b10f3f94871c0d3eb2653dac824c28c269373532d0.
Preparation5cc70880e996740061378c000018f6752533fba63f9db5067399e733a2f6a3eb.
App sha256:cdc77adfdd50a4d3fb4767ee56651ba9a20970b840f9d8da628576e72c61c814;
speech sha256:2b6af090b9bffc5c28a25e1195fe48092513ae10f67299042135789c719e901e.
Exact source-built images/labels, no relabelling old images. Clone warning about
absent default ref was followed by explicit checked detached checkout ofc837c2e.
Stock prepare/profile/inspect PASS; candidateSTAGED_NOT_ACTIVATED,
deployment_authorizedFalse/task_admission_resumedFalse/paid_calls0.
No activation.json exists for the candidate; live binding and deployment remain4f51e27.

Encrypted prepared-package.enc2549143bytes,
SHA1fb11eacc8f3800a112f21497a6ca46ec1b847ab4cdfc840e66666600bc9f5cf.
Protected owner-only PC custody:
C:/Users/Zver/.codex/private-backups/jarvis-2/fragment-prepare-20261127-1906.
Independent PC in-memory decrypt/checksum verifies exact source bundle, candidate
and preparation hashes, every prepared document pin, original production state,
all five original container IDs/StartedAt, retention proposal/restore proofs.
Compared Calendar profile/scopes/keys with protected4f51e27 custody: identical
except expected source_revision; voice profile identical except source_revision/
connection_digest, exact GigaAM manifest unchanged. No plaintext secret files
written or printed; key provided from existing DPAPI custody in memory.
This package contains profiles/keys/source and references to staged images/model,
NOT image/model payloads or a DB dump. It is not a full independent/offsite backup.

## Verified retention proposal, NOT executed

20 server DB backup archives independently decrypted/checksummed;60 protected PC
file copies independently decrypted/checksummed (includes duplicates/history).
14 of the20 server DB archives match protected PC copies; all four proposed
files match size/ciphertextSHA/bundle/created_at/dumpSHA. No raw DB dump exported.
111206315bytes are the20 DB archives;146340120other counted bytes remain untouched.
No assertion that all counted files are DB archives or safe to delete.

The four selected archives are superseded by newer same-bundle files retained on
server. All current4f51e27 and prior73647d0 archives remain. latest pointer stays
backup_787020bb7d274706a658c864a0287067.enc. Four separate rootless networkless
PostgreSQL restores with full stock audit-anchor validation PASS, primary_modified
False. Same bounded512MiB tmpfs/1GiB adapter and final TCP readiness preserve stock
checks; isolated targets removed by stock finally cleanup. No restore over primary,
old application compatibility, offsite custody or RPO/RTO proven.

Private exact plan SHA09131b549f286830f6c0051f7e4bcee01cfcb3eb75dd2ad57c0ef869538c18af.
Adapted the existing operator exact-file retention pattern with a deployment lock,
regular/non-symlink/single-link/owner/mode/size/SHA guards, latest/newest preservation,
per-file journal and directory fsync. Inspection-only mode PASS. Apply requires a
NEW release-authorization.json with exact source/candidate/preparation/plan pins,
explicit retention approval, independent PC proof and a fresh<=1h deadline.
Preparation authorization is deliberately insufficient. No deletion receipt exists.
If execution is interrupted, inspect actual files/receipt before any further action;
never blindly repeat. Restore an archived file exclusively from its exact protected
PC original, owneracc-control/mode0600, verify both checksums. Do not alter
latest.json or restore anything over the primary DB for a file-custody recovery.

## Required next approval and installation plan

Need fresh exact permission for BOTH the four-file server retention and PR128
installation. Preserve this preparation grant; do not change it into deployment
consent. Before execution recheck live4f51e27/journals, exact prepared source/images/
model/Calendar binding, latest/inventory/copy pins and current capacity under lock.
Stop if any precondition changed. Execute only the four approved files, then verify
freed bytes and retained latest/newest copies. No quota increase or broader cleanup.

Then take fresh protected current prebackup and full isolated audit restore/PC
custody verification. Budget stock apply's extra backup plus postbackup using the
fresh actual size and reserve; no quota bypass or reused stale database snapshot.
ONE stock exact prepare-inspect-authorized-install/update; no compose-up substitute.
If the first apply is uncertain, read-only reconcile actual result; stock reconcile
only when exact target and every pre/postcondition pass. No blind apply retry or
manual application journal changes. Resume through the actual owner Telegram path,
old cancelled jobs remain cancelled. No paid AI or new Calendar action.

Live fragment-edit acceptance may use only an owner-confirmed wording correction
through an actual observed Reply. Original raw text remains; corrected readback
must stay unaccepted if it contains the owner's test meeting or unresolved fields.
No guessed site/domain, no fake owner Update, no automatic meeting save. Distinguish
new preview validation from complete saved-record or ASR-accuracy acceptance.
Do not manufacture a successful phone/ASR test from CI or this preparation.

Partial-correction provenance is new: predecessor4f51e27 is expected to reject
pending partial cards via its old full-text equality guard. No automatic rollback
compatibility assumed from unchanged SQL schema. Preserve source/audit/queue and
verified backups; exact forward repair or separately approved compatible recovery.

Final read-only health19:17:29UTC: live4f51e27, both VERIFIED, OPENepoch97,
actual4/reserved0/uncertain0; Telegram heartbeat19:17:18.718330, voiceIDLE
19:17:28.681202. Same five container IDs/StartedAt since the previous installed
release, no new stop/OOM or replacement in this stage. One19:11 network poll failure
consecutive1 recovered, not an indefinite availability claim. Disk21167104000bytes
free; backup quota unchanged10889021bytes free. Stage2 incomplete.

Private operator artifacts: .runtime/voice-fragment-release. Nothing installed.
