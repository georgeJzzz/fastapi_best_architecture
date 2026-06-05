## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `georgeJzzz/fastapi_best_architecture`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo: read root `CONTEXT.md` and root `docs/adr/` when present. See `docs/agents/domain.md`.

### Development language

When working in a Chinese development context, use Chinese for agent-facing explanations and code comments added or changed by the agent.

### File reading hygiene

When scanning or reading project files, prefer `.gitignore`-aware file discovery such as `rg --files`. Do not read IDE metadata, Git metadata, cache folders, or generated Python bytecode directories such as `.idea/`, `.git/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, and `__pycache__/` unless the user explicitly asks for those files.
