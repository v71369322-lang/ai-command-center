# Planning candidate / activation operator checkpoint

Branch `feat/planning-candidate-preparation` depends on #93. Parent exact
`c63a815d718aee06dc5e67a2eced827334fa3c29` full F1/F2 synthetic CI SUCCESS was
observed before completing this stage. Main remains f5ff8b2; no merge/deployment.

Closes the operational gap between disabled release preparation and the protected
planning binding: derives private profile/host, target source/image metadata,
staged Telegram connection, raw/semantic pins and immutable blocked review.
Requires real fresh operator evidence and independent key fingerprint; it reads
only key descriptor metadata. Candidate completion marker is written last in a
new private directory; inspection checks custody, inventory, hashes, scope and
known journal provenance without changing files or contacting providers.

Adds a planning adapter on the existing Telegram transition / Deployment.apply
and Deployment.reconcile_intent. Requires exact previous/candidate/preparation
and separate control-capability pins plus bounded expiry. Normal stop/drain is
before connection replacement. Legacy memory apply cannot bypass planning access
approval. Planning postchecks additionally require halted admission, fresh target
worker, no runtime rows, no recovery/uncertain reserve, anchored external ledger
and COMPLETE/zero-reserve actions. No paid authority is created or old tasks
resumed. Unknown apply cannot be replayed; only exact independently healthy target
INTENT/DEPLOYMENT_ATTEMPTED reconciliation is supported, without runtime/binding
changes or manual journal substitution.

Operator workflow: [CANDIDATE_ACTIVATION.md](../planning/CANDIDATE_ACTIVATION.md).
Control Docker socket remains administrative capability; exact deployment/access
authorization is still required before actually installing it.

Initial locked validation: candidate/binding/release 136 passed; candidate,
activation and legacy adapter selected scope 51 passed; real PG/SQLite additional
health scope 9 passed. The first two overlap; do not add them. Ruff and existing
Bandit triage passed, with security scope extended to the new operator scripts
and modified legacy adapter. The fixed in-container tmpfs target has the same
documented B108 false-positive treatment as the existing deployment profile;
no host temporary file is created and no gate or reviewed-rule list was relaxed.
Broader clean-source checks, image metadata smoke and final exact CI are recorded
in the resulting dependent Draft PR; synthetic/rootful checks are not rootless
or VPS acceptance.

Owner confirmed **operator profile does not yet exist**. No real profile, tariff,
model, funding balance, fingerprint or data-sharing evidence has been invented.
No provider key bytes, paid AI, VPS state, runtime socket ACL, deployment, real
binding or external project was touched. A real live candidate remains blocked
on fresh protected operator inputs, exact built/inspected target images and a
separate exact owner deployment/access decision. Do not treat this checkpoint or
a fixture package as deployment or spending permission.
