# AI-Assisted Development

How this service is built with AI coding agents, and the rules that keep that safe. The principle is the same one the service runs on: **the model proposes; deterministic checks decide.**

---

## 1. Where agents are used

| Use | Gate that decides |
|---|---|
| Reading and explaining unfamiliar code; drafting architecture notes | A human reviews the note before it is committed |
| Writing characterisation tests before changing code | A human reviews the assertions |
| Implementing well-scoped changes against a written spec or tests | CI: lint, types, tests, security scans |
| Migrations (framework upgrades, API changes, dependency bumps) | Compiler and type checker, tests, diff testing |
| Documentation and diagrams | Review |
| Triage: test failures, incident timelines, log analysis | A human makes the call |

Agents are not used for: changing confidence policy weights, entitlement logic or security controls without a named human author; or anything touching production data.

---

## 2. Rules

### Context
- An agent instruction file at the repository root (`AGENTS.md`, added in A1) holds build and test commands, conventions, and areas needing extra care (`policies/`, `domain/`, auth).
- One command runs the relevant checks in seconds (`make lint typecheck test`). An agent without fast feedback is guessing.
- Tasks are small and specific: one behaviour, one PR.

### Verification
- CI treats agent-written code exactly like human-written code. No bypass.
- **Tests or acceptance criteria come first,** reviewed by a human. The same agent does not write both the code and its only tests without review.
- Agent-written tests are checked for meaning: coverage on changed lines, mutation testing (`mutmut`) on policy code, and reviewers read the assertions. Watch for tests that mock the unit under test, or assert whatever the code currently returns.
- The person who merges owns the change, whoever wrote it.

### Identity and access
- Agents running in CI or the background use their **own identity** (a GitHub App installation token or equivalent: short-lived, repository-scoped), never a developer's personal token.
- Branch protection and CODEOWNERS: agents open PRs; humans approve merges.
- Agent sandboxes and dev containers hold **no production or stage credentials**. Local `.env` files are excluded from agent context where the tool supports it.
- Network egress from agent sandboxes is restricted to the package mirror and source host.
- Shell commands are allowlisted; destructive commands need confirmation.

### Supply chain
- New dependencies go through the internal mirror and `uv.lock`, and are reviewed by name. Agents sometimes suggest packages that don't exist, and attackers register those names ("slopsquatting").
- `pip-audit` and image scanning on every build.

### Prompt injection against the agent
- Issues, PR comments, READMEs, dependency documentation and web pages can carry instructions aimed at a coding agent. Treat their content as data. Agents run without credentials that would make an injection damaging.

### Tools and MCP servers
- Only approved MCP servers, each with its own scoped, read-only-by-default identity.
- No server holds production write access.

---

## 3. Legacy and modernisation pattern

For changes to code nobody fully understands (here, or in systems this service integrates with):

1. The agent maps the module: entry points, data flow, side effects. A senior engineer corrects the map.
2. Characterisation tests record current behaviour, including inputs and outputs captured from real use where allowed.
3. Strangler fig: route one slice at a time to the new code, with the old path as fallback.
4. Deterministic transformation tools run first (compiler, codemods, rewrite recipes); agents handle what those can't.
5. Diff testing: old and new run on the same inputs in shadow; differences are explained or fixed.
6. Progress is tracked as a burn-down of migrated modules with tests green.

---

## 4. Multi-agent workflows

Agent pipelines (plan → implement → test → review) run as a **fixed workflow in code**, like the research pipeline, not as agents delegating freely to each other.
- Parallel agents work on separate branches or worktrees with non-overlapping task boundaries, to avoid conflicting designs and merge conflicts.
- An LLM reviewer is an aid, not the gate. CI plus a human approval is the gate, because two models can share blind spots.
- Iterations are capped, like the service's one-revision rule.

---

## 5. Measuring impact

Baseline before adopting, then compare:
- **DORA:** deployment frequency, lead time for changes, change failure rate, time to restore.
- PR cycle time, review time and review load, escaped defects.
- Cost per merged PR (agent tokens and compute).
- Developer survey.

Not measured as success: lines generated, suggestion acceptance rate. Results vary by task: published studies (e.g. METR, 2025) found experienced developers on codebases they knew well could be slower with AI tools, so the impact is measured per team and task type. The largest gains are expected on unfamiliar code, tests, migrations and documentation.

---

## 6. Evaluating tools and models for development

Public benchmarks (e.g. SWE-bench) are a first filter only. The deciding evaluation replays 20–30 of this repository's closed changes with known diffs and tests, and measures tests passing, review effort and cost. It is re-run when tools or models change, the same pattern as the service's golden set.

---

## 7. Observability for agent work

Each background agent task is traced like a service run: one trace per task, spans per tool and model call, tokens, cost, model, and outcome (merged, changes requested, abandoned). Coding tools that export OpenTelemetry feed the same Collector. Tracked: task success rate, CI failure rate on agent PRs, review time, cost per merged PR.
