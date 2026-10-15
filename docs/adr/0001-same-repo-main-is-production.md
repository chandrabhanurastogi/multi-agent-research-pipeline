# 0001. Same repo; `main` is the production line

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** —

## Context
The take-home version is complete and was shared with an interviewer. The production version builds on the same code (agents, policies, domain types, tests).

## Decision
Keep one repository. Freeze the take-home as branch `take-home` and annotated tag `v0.1.0-takehome`. `main` becomes the production line. The interviewer is given the tag URL.

## Alternatives considered
| Option | Why not |
|---|---|
| New repository | Loses the history that explains why the policies are the way they are; duplicates code we keep |
| Production work on a `production` branch, `main` frozen | Inverts the normal convention; CI/CD branch rules expect `main` to be the integration branch |

## Consequences
- The take-home stays reachable and unchanged through the tag.
- `main` may be mid-change at any time; anything shared externally points at a tag.
