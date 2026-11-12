# Offline operator profile preparation

This tool turns explicitly reviewed operator facts into the existing unbound
`PlanningProfile`. It creates no grant, key, credential binding, API connection,
deployment or spending permission. Existing API credentials need not be replaced
just because the planning profile does not exist.

Use the dedicated unprivileged Linux operator and a canonical private directory.
Create `operator-evidence.json` under an owned 0700 directory with file mode 0600,
regular/single-link and without symlinks. No credential values belong in this
document. The tool has no key-path argument and rejects common accidental OpenAI
credential shapes in metadata. That detection is not a universal secret scanner.

```sh
PYTHONPATH=src python infra/vps/prepare_planning_operator.py template
PYTHONPATH=src python infra/vps/prepare_planning_operator.py check-input \
  --input-file /private/operator/operator-evidence.json
```

The template intentionally contains
null financial/model/evidence fields and `reviewed: false`; it cannot create a
usable profile. Context/output token limits are conservative technical defaults,
not an account balance, price, FX quote or authority to spend.

Required facts include:

| Input | Meaning |
| --- | --- |
| `model` | Reviewed exact model/snapshot identifier; no automatic latest-model substitution |
| `usd_input_upper_per_million` | Confirmed upper price for all applicable input/cache-write billing |
| `usd_output_upper_per_million` | Confirmed upper output-token price |
| `usd_fixed_upper_per_request` | Confirmed upper fixed charge, explicitly zero if none |
| `rub_per_usd_upper` | Explicit reviewed RUB/USD cost ceiling, not an automatically fetched rate |
| `pricing_evidence`, `fx_evidence` | References supporting those upper bounds |
| `available_rub` | Confirmed spendable RUB envelope supported by funding evidence |
| `per_plan_limit_rub`, `daily_limit_rub`, `monthly_limit_rub` | Explicit owner ceilings, each within the current 100-RUB profile bound |
| `evidence` | Existing account/model/funding/data-sharing references and observed/expiry timestamps |

All monetary/rate values are decimal **strings**, not floating point JSON numbers.
No NaN, exponent notation, negative values or ambiguous currency coercion is
accepted. Funding in USD alone is not a reviewed RUB envelope or a spending grant.
The account balance and account/model access are not queried by this tool.
Public list prices alone do not establish private account funding, custom rates,
data sharing, exchange policy or current model access.

Evidence must already be reviewed, current and bounded to at most 24 hours. The
creator preserves its timestamps; running the tool never extends them. Numeric
`1` is not accepted in place of the literal review flag `true`. Parameter review
is not F1 approval, credential access, deployment approval or paid consent.

## Conversion and custody

An exact independently reviewed raw SHA256 is required for creation:

```sh
PYTHONPATH=src python infra/vps/prepare_planning_operator.py prepare \
  --input-file /private/operator/operator-evidence.json \
  --approved-input REVIEWED_RAW_SHA256 --output /private/prepared-operator-profile
```

The creator uses Decimal arithmetic, rounds each converted per-token/fixed rate
**up** to whole nano-RUB and each available amount/limit **down**. It reuses the
existing Tariff/PlanningProfile validators and verifies the calculated maximum
against all envelopes including the explicit per-plan ceiling. It does not
silently clip large limits, invent a rate or increase any existing bound.

Output must be a new 0700 directory outside the source tree under an owned private
canonical parent. `profile.json`, normalized `operator-evidence.json` and
`conversion.json` are written 0600; `creation.json` is written last. Interrupted
outputs are not overwritten or treated as complete. The conversion report retains
input digest, source references, rounding policy and ceiling calculations.
The original reviewed raw input hash is retained as provenance, while file hashes
refer to the normalized output serialization. A receipt digest is an integrity
pin, not an owner signature or authority.

```sh
PYTHONPATH=src python infra/vps/prepare_planning_operator.py inspect \
  --directory /private/prepared-operator-profile --approved-creation CREATION_DIGEST
```

Inspection is read-only. It checks exact private inventory, file hashes, freshness
and independently repeats the conversion; even a resealed runtime-bound profile
is rejected. Errors and incomplete-input diagnostics omit input values, arbitrary
unknown JSON key names and validation context. No provider key, client, Store,
gateway, SSH or Docker operation is needed.

Pass the resulting `profile.json` and returned raw SHA256 to the existing
[candidate preparator](CANDIDATE_ACTIVATION.md). It binds runtime/source/image and
an independently supplied credential fingerprint. Actual deployment/access
decisions and the observed one-call Telegram financial approval remain separate.
