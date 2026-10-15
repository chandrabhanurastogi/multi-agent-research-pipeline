# 0005. Generic Jenkins / Helm / Vault templates

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** plan phase B

## Context
The organisation's Java services use Jenkins, Helm, Vault and OpenShift, with branch-to-environment rules (dev, sit, stage, prod) and release candidates from release branches. Their exact shared library and chart conventions are not available to this project.

## Decision
Write standard, self-contained templates: a declarative Jenkinsfile that calls `make` targets, a Helm chart with per-environment values files, and Vault Agent annotations. Keep them easy to swap for the organisation's shared library later.

## Alternatives considered
| Option | Why not |
|---|---|
| Copy the Java services' templates | Not available now; can replace the generic ones later |
| GitHub Actions / Argo CD | Not the organisation's toolchain |

## Consequences
- All build logic lives in `make` targets, so moving to a shared Jenkins library changes only the Jenkinsfile.
