# 0006. uv for dependency management

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** SEC-5, MNT-1; plan step A1

## Context
Today `pyproject.toml` has unpinned dependencies and no lock file, so two builds can install different versions. Enterprises build from an internal package mirror (e.g. Artifactory) and need reproducible images.

## Decision
Use **uv**: `uv.lock` committed; `uv sync --frozen` in CI and the Dockerfile (fails if the lock is out of date); the package index set by configuration (`UV_INDEX_URL` / `[[tool.uv.index]]`) so CI points at the internal mirror; Python pinned to 3.12 in `.python-version`.

## Alternatives considered
| Option | Why not |
|---|---|
| pip + `requirements.txt` (pip-tools) | Works, but two files to keep in sync and slower resolution |
| Poetry | Mature, but slower and its own lock format; no advantage here |

## Consequences
- Developers install uv; `make` targets wrap uv so CI and laptops run the same commands.
- Dependency upgrades become explicit commits (`uv lock --upgrade-package ...`), reviewable and scannable.
