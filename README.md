# ai-command-center
Personal AI orchestration and management platform

Start a cloud task with [current status and handoff](docs/STATUS.md) and
[agent instructions](AGENTS.md). They distinguish the tested cloud branch,
last reported VPS version, blocked operations and project migration snapshots.
Do not use main as the implementation base without checking the dependent PRs.

Cloud F1 implementation and safe synthetic runbook: [docs/f1](docs/f1/README.md).
This is not full MVP acceptance or authorization to deploy to a VPS.

F2 bounded synthetic coding cycle, mobile controls and provider limitations:
[implementation](docs/f2/IMPLEMENTATION.md), [validation](docs/f2/VALIDATION.md).
Only mock AI and mock PR publication are enabled; real Git edits and tests run
in isolated containers. No real business repositories are connected.
