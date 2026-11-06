# Security and Governance

Who each call runs as, what it may touch, how models and data are governed, and how we prove it afterwards. It implements SEC and DATA in [NFR.md](NFR.md), with [ADR 0002](adr/0002-llm-access-through-enterprise-gateway.md), [0008](adr/0008-oidc-authentication-keycloak-locally.md) and [0013](adr/0013-guardrails.md).

---

## 1. The core risk: a privileged worker acting for a less-privileged person

A customer may see public market research but not another client's documents. The worker that executes runs can technically query the whole search index. If it searches **as itself**, any customer's briefing can quote anything in the index. This is the **confused deputy** problem, and a prompt injection that asks for "everything about client X" makes it exploitable.

The rule: **the worker authenticates as itself, but authorises data access as the person it acts for.** Entitlements are enforced inside the search engine's query, so a bug in our code cannot return a document the search engine was never allowed to return.

---

## 2. Identities

| Identity | Who | Authenticates with | Used for |
|---|---|---|---|
| **Customer** | End users in customer channels | OIDC token from the customer identity platform (CIAM), presented by the channel | Who asked; document entitlements; rate limits |
| **Staff** | Analysts, reviewers, operators | OIDC token from the corporate identity provider | Same, plus review and admin roles |
| **Calling service** | Channel back ends that submit on a user's behalf | OAuth2 client credentials or mTLS, with the user's token forwarded or exchanged | Which channel; per-channel quota |
| **Workload** | `research-api`, `research-worker`, `research-migrator` pods | Kubernetes ServiceAccount → projected, audience-bound, expiring token → Vault or cloud IAM | Infrastructure access only |
| **CI/CD** | Jenkins jobs | Short-lived, per-environment tokens (OIDC federation or Vault) | Build, push, deploy |

The API validates every token (issuer, audience, expiry, signature) and records the user and the calling service on the run (SEC-1, DATA-1).

---

## 3. Credential map

| Caller → target | Credential | Least privilege |
|---|---|---|
| User → API | OIDC access token | Create runs; read own runs (or team runs if configured) (SEC-2) |
| API → Postgres | Dynamic credentials from Vault's database engine, short TTL | Insert jobs and runs, read runs; no DDL |
| Worker → Postgres | Separate dynamic credentials | Claim jobs, write runs and checkpoints; no DDL |
| Migrator → Postgres | Migration role, used only by the Helm hook | DDL; not mounted in api or worker pods |
| Worker → LLM gateway | Scoped virtual key or client credentials from Vault; ideally workload identity with no stored secret | Approved model aliases, team budget, rate limit |
| Gateway → model provider | Owned by the AI platform team, ideally keyless (cloud IAM) | Never visible to this service |
| Worker → search | Service credential **plus** the user's entitlements in the query | Read-only on the index |
| Worker → object storage | Bucket-scoped credential | Write and read under the service prefix |
| Pods → Collector | Network policy, optional mTLS | Egress only to declared dependencies (SEC-7) |
| Jenkins → registry and cluster | Per-environment short-lived tokens | A dev pipeline cannot deploy to prod; prod needs approval |

### Service accounts
- One ServiceAccount per workload; never the namespace `default`.
- `automountServiceAccountToken: false`: the application never calls the Kubernetes API, so it needs no RBAC role.
- Vault's Kubernetes auth method verifies the projected token and returns a short-lived Vault token bound to a per-workload policy.
- Where the platform supports it, **workload identity** (GKE Workload Identity, EKS Pod Identity / IRSA, Azure Workload Identity, or SPIFFE/SPIRE) replaces stored secrets entirely.
- Credentials are fetched at runtime and expire, so rotation is routine. The identity that deploys is not the identity that runs.

---

## 4. Carrying the user's identity to the worker

The request ends at the API; the worker runs later. In order of strength:

| Option | How | Trade-off |
|---|---|---|
| 1. Entitlements on the job | The API stores user ID and entitlement groups on the job | Simple. Access revoked mid-run is honoured only after the run ends; bounded by the 10-minute run limit (LAT-3) |
| 2. Re-resolve in the worker | The worker looks up the user's groups when the run starts and before each search | Fresh; adds a directory dependency to the hot path (cache with a short TTL) |
| 3. Token exchange (RFC 8693) | The API exchanges the user's token for a short-lived token for the search service, naming both the user (`sub`) and the worker (`act`) | Strongest and auditable at the search service; needs identity-provider support |

**Launch with option 2,** with the entitlement-set hash on the job for caching, and move to option 3 when the identity team supports token exchange. Stored briefings are re-checked on read, so a user whose access was revoked cannot open a briefing built from documents they can no longer see.

---

## 5. What agents are allowed to do

- **No write tools.** Agents read the documents they are given and return typed output. None can send, write, delete, pay or call external systems. Any future tool needs a design review.
- **Code decides; the model proposes.** IDs, tiers, scores, entitlements and control flow are set by code. The same principle applies to any future tool call: a policy check authorises it, not the model.
- **Bounded consumption:** at most 15 LLM calls, 100k tokens and 10 minutes per run (COST-2, LAT-3); exactly one revision.
- **Human approval for irreversible actions:** the LangGraph `interrupt()` pattern (A7) is the mechanism if any is added.
- **MCP servers** (if used): only from an approved list; each with its own scoped identity; tokens bound to that server's audience and never passed through to other APIs (MCP authorization spec, OAuth 2.1); read-only by default.

---

## 6. LLM-specific risks (OWASP Top 10 for LLM Applications, 2025)

| Risk | Where it applies | Control |
|---|---|---|
| LLM01 Prompt injection | Documents and questions containing instructions (sample corpus S12) | Documents passed as delimited data; the model has no authority over IDs, tiers, scores or entitlements; injection cases in the golden set (QUAL-4); gateway guardrails (ADR 0013) |
| LLM02 Sensitive information disclosure | A briefing quoting a document the user may not see; PII in prompts | Entitlement filter in search; re-check on read; Presidio masking before model and logs (SEC-9) |
| LLM03 Supply chain | Compromised package, unapproved model | `uv.lock`, internal mirror, `pip-audit`, SBOM, image scan; approved models only via the gateway |
| LLM04 Data and model poisoning | Planted documents in the corpus | Governed ingestion; tier and origin set by people; low tiers down-weighted |
| LLM05 Improper output handling | Model output rendered or used downstream | Pydantic validation of every output; escaped rendering |
| LLM06 Excessive agency | Tools beyond need | No write tools; fixed workflow in code |
| LLM07 System prompt leakage | Prompts exposing internals | No secrets or entitlement data in prompts; prompts are versioned and reviewed |
| LLM08 Vector and embedding weaknesses | Vector search ignoring access control (A8) | Entitlement filter inside the hybrid query; per-tenant index security |
| LLM09 Misinformation | Confident, wrong briefing | Trust boundary, Verifier, rule-based confidence, gaps shown, review flags |
| LLM10 Unbounded consumption | Loops, abusive clients, cost spikes | Per-run budgets; per-customer and per-channel rate limits (CAP-5); gateway quotas |

### Abuse at customer scale
- Rate limits per customer, per channel and per IP range at the API gateway, plus bot detection where the channel provides it.
- Question-length limits (CAP-3), and input guardrails for disallowed content before any model call.
- Anomaly alerts: one customer with an unusual share of runs; repeated injection-pattern inputs.

---

## 7. Model governance

- **Approved models only,** from the gateway's list, under terms that exclude training on our data (DATA-3), in approved regions (DATA-4).
- **Pinned versions:** each agent uses an alias mapped to a pinned model version at the gateway. "Latest" aliases are not allowed in stage or prod.
- **Changes are releases:** a model, prompt, retrieval or orchestration change passes the evaluation gate (QUAL-5), then goes through shadow and canary (see [OPERATIONS.md](OPERATIONS.md)).
- **Fallback policy:** fallback keeps the service available, but a briefing whose Synthesiser or Verifier ran on a fallback model is not published without review in stage and prod (ADR 0010).
- **Provider deprecations** are tracked with dates, like dependency end-of-life, with replacement evaluation started at least 6 weeks ahead.
- **Documented limitations:** the README section "What it fundamentally cannot do" is the model limitation statement and is reviewed with each release.

---

## 8. Data governance and audit

- **Audit record per run (DATA-1):** user and calling service, time, question, plan, sources and exact quotes used, rejected claims with reasons, model and prompt version per step, verdicts, scores, final briefing, `trace_id`.
- **Retention (DATA-2):** run summaries 1 year in day-partitioned tables; full artifacts 90 days in object storage; traces no longer than the run records they describe.
- **Residency:** data and model calls stay in approved regions; the gateway routes only to models in those regions.
- **Data subject requests:** run records are keyed by user ID, so they can be found and deleted on request.
- **Transparency:** support labels read "Strongly supported *by our sources*", never as a probability. Briefings that need review say so.
- **Human oversight:** `review_required` briefings are visibly marked, and a sample of high-impact briefings is reviewed by analysts (QUAL-6).

### Reference frameworks
- **NIST AI RMF** (Govern, Map, Measure, Manage): NFRs, ADRs, the evaluation gate and run records provide the Measure and Manage evidence.
- **ISO/IEC 42001**: the AI management system standard, if the organisation certifies against it.
- **EU AI Act** and sector rules (e.g. model risk management in financial services): risk classification and current obligations are confirmed with legal and compliance before launch.

---

## 9. Ownership

| Concern | Owner | This team's part |
|---|---|---|
| Provider credentials, approved models, model throughput | AI platform team (gateway) | Request aliases, capacity and budget; record the answering model |
| Customer and staff identity, groups | Identity team | Register OIDC clients; validate tokens; enforce access per run |
| Document entitlements, source tiers and origins | Content owners and compliance | Enforce in search; never let a model set them |
| Confidence policy weights | Analysts and compliance | Implement, test, version and publish the rule |
| This service's secrets and service accounts | This team | Vault paths, policies, rotation, least privilege |
| Tracing platform and its retention | Observability team | Instrument, redact, choose what is sent |
| Edge rate limits, WAF, bot detection | API gateway / edge team | Define per-customer and per-channel limits |

---

## 10. Pre-launch security checklist

- [ ] Threat model reviewed: data flows, trust boundaries, identities above
- [ ] Every token validated; tests for expired, wrong-audience and wrong-issuer tokens
- [ ] Entitlement tests: a user without access never sees a restricted document in claims, briefing or cache (SEC-3)
- [ ] No secret in code, image, logs or ConfigMaps (`gitleaks`, image scan) (SEC-4)
- [ ] No critical vulnerabilities; SBOM published (SEC-5)
- [ ] Restricted SCC, non-root, read-only root filesystem (SEC-6)
- [ ] NetworkPolicy egress allowlist (SEC-7)
- [ ] Injection and PII cases pass in the golden set (SEC-8, SEC-9)
- [ ] Penetration test of the API, including rate-limit bypass
- [ ] Audit record and retention verified with compliance (DATA-1, DATA-2)
