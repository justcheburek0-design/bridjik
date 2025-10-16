# Repository Guidelines

This document provides contributor guidance for the minebridge repository. Keep changes focused, well‑tested, and consistent with the style below.

## Project Structure & Module Organization
- Source code: `src/minebridge/` (preferred) or `minebridge/`.
- Tests: `tests/` mirroring package structure (e.g., `tests/test_utils.py`).
- Scripts & tooling: `scripts/` for one‑off helpers; configs in `pyproject.toml`/`setup.cfg`.
- Assets/data: `assets/` or `examples/` (avoid committing large/generated files).

## Build, Test, and Development Commands
- Create env (Windows): `python -m venv .venv && .\.venv\Scripts\Activate`
- Create env (Unix): `python -m venv .venv && source .venv/bin/activate`
- Install (dev): `pip install -U pip` then either `pip install -e .[dev]` or `pip install -r requirements.txt` (plus `-r requirements-dev.txt` if present).
- Run package: `python -m minebridge` (or call specific modules, e.g., `python -m minebridge.cli`).
- Test: `pytest -q`
- Lint/format: `ruff check .` • `black .` • `isort .` • optional types: `mypy src/`.

## Coding Style & Naming Conventions
- Python: 3.10+ with type hints. Keep functions small and pure when possible.
- Formatting: Black (88 cols), isort (profile=black). Lint with Ruff; fix before committing.
- Naming: modules/functions `snake_case`, classes `CamelCase`, constants `UPPER_SNAKE_CASE`, internal APIs prefixed with `_`.
- Docstrings: concise, Google‑style or reST; include parameters, returns, and side effects.

## Testing Guidelines
- Framework: `pytest` with `tests/test_*.py`; shared fixtures in `tests/conftest.py`.
- Coverage: target ≥80%. Run `pytest --cov=minebridge --cov-report=term-missing` if coverage is configured.
- Practices: unit first; mock I/O and network; use `tmp_path` for filesystem; avoid flakiness and sleeps.

## Commit & Pull Request Guidelines
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Keep messages imperative and scoped (e.g., `feat(api): add bridge sync`).
- PRs must: describe motivation/approach, link issues, include tests/docs, pass CI, and note breaking changes. Add screenshots/logs for user‑visible changes.

## Security & Configuration Tips
- Never commit secrets; use `.env` (local) and keep `.env.example` updated.
- Pin critical deps and audit periodically (e.g., `pip-audit`).
- Large/derived artifacts belong in releases or storage, not in Git.

## Agent‑Specific Notes
- Scope: This AGENTS.md applies repo‑wide. Prefer minimal, surgical changes.
- Before large edits, scan for additional `AGENTS.md` files in subdirectories and follow the most specific guidance.
