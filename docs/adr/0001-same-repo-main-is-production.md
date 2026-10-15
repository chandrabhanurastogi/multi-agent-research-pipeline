# 0001. Single repository; `main` is the production line

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** —

## Context
The v0.1.0 reference implementation (CLI pipeline, agents, policies, domain types, offline tests) is complete. The production service builds on the same code rather than replacing it.

## Decision
Keep one repository. Tag the reference implementation as `v0.1.0`. `main` is the production integration line; releases are cut from it by tag.

## Alternatives considered
| Option | Why not |
|---|---|
| New repository | Loses the history that explains why the policies are the way they are; duplicates code we keep |
| Production work on a `production` branch, `main` frozen | Inverts the normal convention; CI/CD branch rules expect `main` to be the integration branch |

## Consequences
- The reference implementation stays reachable and unchanged through the `v0.1.0` tag.
- `main` may be mid-change at any time; anything shared externally points at a release tag.
