# 0008. OIDC authentication; Keycloak locally

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** SEC-1, SEC-2, SEC-3, DATA-1; plan steps A2, A8

## Context
The take-home has no users. Production needs to know who asked (audit), restrict who can read a run, and filter documents by the user's groups (entitlements).

## Decision
- The API validates **OIDC access tokens (JWT)** itself: signature against the provider's JWKS, issuer, audience, expiry. User ID and groups come from token claims.
- The provider is configuration (`OIDC_ISSUER_URL`, `OIDC_AUDIENCE`, groups claim name). Locally **Keycloak** with a committed realm export (test users and groups); in clusters the corporate identity provider.
- Health endpoints are unauthenticated; everything under `/v1` requires a token.
- Library: PyJWT with its JWKS client (small, widely used); revisit if the organisation mandates another.

## Alternatives considered
| Option | Why not |
|---|---|
| Authentication only at the edge (OAuth proxy on the Route) | We still need user ID and groups inside the app for audit and entitlements; validate in the app as defence in depth (an edge proxy can be added too) |
| Static API keys | No user identity, no groups, keys get shared |
| Add authentication later | Run records, entitlements and audit all depend on identity; retrofitting touches everything |

## Consequences
- Local stack gains a Keycloak container; tests use locally signed tokens, no Keycloak needed.
- Phase B needs an OIDC client registered with the identity team.
