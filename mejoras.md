# MultiAgent — Improvement Roadmap (WAVEs)

This document is a roadmap of atomic, independently-executable improvement tasks ("waves") for the MultiAgent repository. It was produced by exploring both `MultiAgent` (this repo) and `Trend-AI/` (a separate, unrelated project that happens to live in this repo as a reference — see Appendix C) and cross-referencing findings against verified `path:line` locations.

Format is adapted from `Trend-AI/docs/09-beta/waves/` — a documentation-led, contract-first wave template written for coding agents. Every claim below was verified by reading the cited file; no edge was invented.

---

## How to execute a wave

1. **Read this whole section first, then only your assigned wave.** Do not read sibling waves unless your wave's `Dependencies` says to — each wave is self-contained by design.
2. **Check `Dependencies` before starting.** If a dependency wave has not landed, stop and say so; do not improvise a substitute.
3. **Respect `Scope → explicitly out of scope`.** Several files are edited by more than one wave (see Risks section). Touching a file outside your wave's scope is the single most likely way to create a merge conflict with a sibling wave.
4. **Documentation impact is not optional.** Every wave that changes a fact stated in `systems.md` must update the exact section(s) named in its `Documentation impact` field, *before* marking acceptance criteria complete. `systems.md` is read as context by every subsequent wave — a wave that leaves it stale corrupts the next agent's understanding, not just the docs. The full cross-cutting pass (fallback DAG redraw, budget math recomputation) is WAVE-16's job, not yours — you only need to fix the facts your wave itself changed.
5. **No live network calls in tests unless explicitly marked.** Tests default to running under `pytest -m "not e2e and not real_ai"` (see WAVE-02). Only mark a test `real_ai`/`e2e` if it must call a live provider, and never let such a test run in default CI.
6. **No commit, no push.** Leave the working tree reviewable. Produce the `Agent deliverable` write-up specified in your wave.
7. **Do not use `git add .`** — stage only the files your wave actually owns.
8. **When your wave's guard tests fail against *existing* data** (this is expected in WAVE-06), backfill the existing data first, then turn the guard on — see that wave's `Implementation sequence`. A wave that lands with red CI because it forgot to backfill is not done.

---

## Binding decisions

These were made explicitly with the user and are not open for re-litigation by an executing agent:

1. **Language: this document, and all new documentation it produces, is English.** (Existing Spanish in `systems.md` §4.3/§4.4 subsection titles may stay as-is unless a wave explicitly touches that content.)
2. **Delete all dead code.** `tasks/` (Celery), `scrapers/` (Scrapy), `tools/selenium_driver.py` (Selenium), `core/requests_client.py` are removed outright, not deprecated-in-place. See WAVE-01.
3. **Windows support = document WSL2, do not build native Windows tooling.** No `.ps1`/`.bat` launchers, no `%APPDATA%` config migration are in scope anywhere in this roadmap. The one exception: the `run_terminal` denylist security hole is fixed regardless of platform strategy, because it is a security defect independent of whether Windows is officially supported (WAVE-04).
4. **Trend-AI porting priority: (a) quality/evals, (b) single-flight cache + budgets.** The prompt-registry pattern (`.md` + frontmatter, `prompt_registry.py`) and the `CapabilityRegistry` circuit-breaker pattern are real, verified, portable ideas — but are **deferred**, not planned. See Appendix A.
5. **Reserved type names** (see Risks §6): `core/` owns `CallOutcome` (WAVE-05). `agents/deep_research/` owns `SourceResultStatus` (WAVE-11). Both are 7-ish-value enums with overlapping member names (RATE_LIMITED, QUOTA_EXHAUSTED, TIMEOUT, ERROR) but are **separate types for separate domains** (LLM call outcomes vs. search source outcomes) and must never be unified into one enum.

---

## Dependency graph

```
WAVE-01  Dead code removal
   |
WAVE-02  Fake provider + markers + keyless CI
   |
WAVE-03  Scenario suite + coverage meta-test
   |
   +------------------+---------------------------+
   |                  |                            |
 TRACK A            TRACK B                     TRACK C
   |                  |                            |
WAVE-04 sandbox    WAVE-09A cache core          WAVE-13 CLI surface
(parallel with 05)    |                            |
   |               WAVE-09B wire fetch_url       WAVE-14 new tools
WAVE-05 router         |                            |
   |               WAVE-10 concurrency              |
WAVE-06 registry       |                            |
   |               WAVE-11 search resilience         |
WAVE-07 quota          |                            |
   |               WAVE-12 lightpanda                |
WAVE-08 providers      |                            |
   |                   |                            |
   +--------> WAVE-15 (needs WAVE-07) <--------------+
                        |
                   WAVE-16 docs (depends on all)
```

Track A is strictly linear except WAVE-04, which may run in parallel with WAVE-05 (no shared files). Track B is strictly linear — `agents/deep_research/source_fetch.py` is touched by four consecutive waves (09B, 10, 11, 12) and reordering them changes behavior, not just file conflicts (see Risks §1). Track C is linear. WAVE-15 has a cross-track dependency on WAVE-07 — this is the one dependency arrow that is easy to miss because it crosses from Track C to Track A.

---

## Wave index

| ID | Title | Depends on | Primary files | Size |
|---|---|---|---|---|
| WAVE-01 | Dead Code Removal and Dependency Slimming | — | `tasks/`, `scrapers/`, `tools/selenium_driver.py`, `core/requests_client.py`, `docker-compose.yml`, `Dockerfile`, `requirements.txt` | M |
| WAVE-02 | Deterministic Test Harness and Keyless CI | 01 | `tests/fakes/`, `pyproject.toml`, `.github/workflows/ci.yml` | M |
| WAVE-03 | Agent Regression Scenario Suite | 02 | `evals/scenarios.v1.json`, `tests/test_scenarios.py` | L |
| WAVE-04 | Terminal Sandbox Hardening and WSL2 Policy | 02 | `cli_app/tools.py`, `cli_app/env_setup.py`, `README.md` | S |
| WAVE-05 | Router Reliability: Failure Taxonomy and Retry Budgets | 03 | `core/router.py`, `core/agent_runtime.py`, `agents/deep_research/synthesizer.py` | M |
| WAVE-06 | Provider Registry: Single Source of Truth | 05 | `core/clients.py`, `core/config_editor.py`, `core/quotas.py`, `config/model_benchmarks.yaml`, `config/model_router.yaml` | M |
| WAVE-07 | Quota Ledger: Reserve, Refund, Budgets | 06 | `core/quotas.py`, `core/router.py` | M |
| WAVE-08 | Free Provider Catalog Expansion | 07 | `config/model_router.yaml`, `config/model_benchmarks.yaml`, `.env.example` | S |
| WAVE-09A | HTTP Cache Core (standalone) | 03 | `core/http_cache.py` (new) | M |
| WAVE-09B | Wire the Cache Into the Fetch Chokepoint | 09A | `agents/deep_research/source_fetch.py`, `core/search_guards.py` | S |
| WAVE-10 | Concurrent Fetching | 09B | `agents/deep_research/source_fetch.py`, `core/search_guards.py` | S |
| WAVE-11 | Search Resilience and Source Status Contracts | 10 | `agents/deep_research/source_fetch.py`, `agents/deep_research/web_search.py`, `config/model_router.yaml` | L |
| WAVE-12 | Optional Lightpanda Rendering | 11 | `agents/deep_research/source_fetch.py`, new `core/render/` | M |
| WAVE-13 | CLI Surface and Agent-Loop Hygiene | 03 | `cli.py`, `cli_app/commands.py`, `cli_app/tools.py`, `cli_app/agent_chat.py` | M |
| WAVE-14 | New Agent Tools | 13, 04 | `cli_app/tools.py`, `config/cli_toolbox.yaml` | S |
| WAVE-15 | Orchestration Research and Concurrent Plan Execution | 07, 13 | `cli_app/orchestrate.py` | M |
| WAVE-16 | Documentation Coherence Pass | all | `systems.md`, `README.md` | M |
| WAVE-17 | Structured CLI Output and Cross-AI Context | 13, 15, 16 | `cli_app/output.py` (new), `cli.py`, `cli_app/commands.py`, `cli_app/tools.py`, `cli_app/agent_chat.py`, `cli_app/pipeline_cli.py`, `cli_app/session.py` | L |
| WAVE-18 | Role Consolidation via Stronger Prompts | 15, 17 | `graphs/vibe_coding_graph.py`, `graphs/deep_research_graph.py`, `agents/vibe_coding/coder.py`, `agents/vibe_coding/debugger.py`, `agents/deep_research/context_compressor.py`, `config/model_router.yaml`, `config/model_benchmarks.yaml`, `core/quota_estimate.py`, `systems.md` | L |

Size legend: S = one focused session, M = one full session, L = may need to split (flagged explicitly where relevant).

---

## WAVE-01 — Dead Code Removal and Dependency Slimming

### Objective
Delete every subsystem with zero live callers, and the infrastructure that exists only to serve them, so every later wave reasons about a smaller, honest codebase and CI installs a lighter dependency set.

### Dependencies
None — can start immediately. Blocks: everything (this is the roadmap's first wave).

### Repository context
Four subsystems have zero callers outside their own package, confirmed by grep:
- `tasks/` (`celery_app.py`, `research_tasks.py`, `scraping_tasks.py`) — `tasks/celery_app.py:5-8` hardcodes `redis://localhost:6379/{0,1}` and **never reads the `REDIS_URL` env var** that `docker-compose.yml` sets on every worker (lines 26, 41, 57 below) — the task queue is already broken as configured, independent of this deletion. Four registered tasks; only `run_gpt_researcher` (queue `research`) has any caller, at `agents/deep_research/gpt_researcher_wrapper.py:48`, and that caller wraps the call in a bare `except (ImportError, ConnectionError, Exception)` that falls back to `_run_research_direct()` in-process at `:73` — i.e. Celery being absent is already a silently-handled, fully-tested code path.
- `scrapers/` (the entire Scrapy project: spider, items, pipelines, middlewares) — zero callers anywhere in `agents/`, `graphs/`, or `cli_app/`.
- `tools/selenium_driver.py` — zero callers.
- `core/requests_client.py` (73 lines) — zero callers. Ironically the best-engineered HTTP client in the repo (connection pooling, `urllib3.Retry`) and nothing uses it.
- `docker-compose.yml` (confirmed by direct read) — **100% Celery/Redis**: one `redis:7-alpine` service plus three `celery-worker-*` services (`default`, `scrapy`, `research`), no other service defined. Deleting `tasks/` and `scrapers/` leaves every service in this file referencing modules that no longer exist.
- `Dockerfile` (confirmed by direct read) — a plain `python:3.11-slim` + `pip install -r requirements.txt` + `COPY . .`. It exists solely to be the build context for the four `docker-compose.yml` services above; nothing else references it.
- `requirements.txt:29-39` (confirmed by direct read) pins `requests`, `scrapy`, `selenium`, `webdriver-manager`, `celery`, `redis` with comments literally naming the directories being deleted (`# Core HTTP client (core/requests_client.py)`, `# Static crawling (scrapers/scrapy_project/)`, `# Headless JS rendering (tools/selenium_driver.py)`). `pyproject.toml`'s `dependencies` list already omits all six — meaning `pip install -e .` (the documented install path) already works without them; only `pip install -r requirements.txt` pulls this dead weight.
- Dead constants inside the live research path: `agents/deep_research/web_search.py:47-78` `SEARCH_RESULTS_FORMATTER_PROMPT` is never referenced — `run_web_search()` makes zero LLM calls. Dead locals in the same function: `router_instance` (param, unused), `focus`, `profile_block`, `facet_block` (computed at lines ~224-250, never read in the `merged` return at ~301-305).

### Scope
**In scope:**
- Delete `tasks/`, `scrapers/`, `tools/selenium_driver.py`, `core/requests_client.py` entirely.
- Delete `docker-compose.yml` and `Dockerfile`.
- Remove `scrapy`, `selenium`, `webdriver-manager`, `celery`, `redis`, and (if truly orphaned after the `requests_client.py` deletion — verify no other file imports `requests`) `requests` from `requirements.txt`.
- Rewrite `gpt_researcher_wrapper.py` to call `_run_research_direct()` directly — no Celery branch, no `try/except ImportError` dance.
- Delete the dead `SEARCH_RESULTS_FORMATTER_PROMPT` constant and the dead locals in `agents/deep_research/web_search.py`.

**Explicitly out of scope:**
- The fate of the `deep_research.web_search` *role* (config entry, quota reservation, benchmark rows) — that is WAVE-11's decision, not this wave's. This wave only removes dead *code paths* inside the function body, not the config surface.
- Any change to `agents/deep_research/gpt_researcher_wrapper.py`'s retry/error semantics beyond removing the Celery branch — that belongs to WAVE-05.
- `core/agent_runtime.py`, `core/router.py` — untouched here.

### Mandatory inspection
Before editing, read: `tasks/celery_app.py` in full (confirm no other queue/task is silently load-bearing), `agents/deep_research/gpt_researcher_wrapper.py` in full, `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `pyproject.toml`, and grep the whole repo for `import requests`, `from scrapers`, `from tools.selenium_driver`, `celery`, `Celery` to confirm zero remaining references before deleting.

### Implementation sequence
1. Grep-confirm zero remaining callers for each of the four dead subsystems (do this even though it was confirmed during planning — code may have changed).
2. **Transcribe `core/requests_client.py`'s conventions into this wave's `Agent deliverable` before deleting it**: its timeout defaults, retry/backoff configuration (`urllib3.Retry` parameters), connection pool sizes (`pool_connections`, `pool_maxsize`), and default User-Agent string. WAVE-09A will re-implement equivalent behavior from scratch and git history is not a reliable source for a future agent to consult mid-session.
3. Delete `tasks/`, `scrapers/`, `tools/selenium_driver.py`, `core/requests_client.py`.
4. Delete `docker-compose.yml`, `Dockerfile`.
5. Edit `requirements.txt`: remove the six lines under `# --- HTTP / Scraping ---` and `# --- Background Tasks ---`; keep `gpt-researcher>=1.0.0` (still used, in-process).
6. Rewrite `agents/deep_research/gpt_researcher_wrapper.py` — delete the Celery `.delay()` attempt and its exception handling; call `_run_research_direct()` unconditionally. Preserve its existing signature and return shape exactly (callers in `graphs/deep_research_graph.py:514-518` must not need changes).
7. Delete `SEARCH_RESULTS_FORMATTER_PROMPT` and the dead locals in `web_search.py`; re-read `run_web_search()`'s `merged` return statement afterward to confirm nothing else referenced them.
8. Run the existing test suite (whatever exists before WAVE-02 lands) and fix any import errors surfaced by the deletions.

### Contracts
No new contracts. `gpt_researcher_wrapper`'s public function signature and return type must be byte-for-byte unchanged from the caller's perspective.

### Mandatory tests
Run the full existing `pytest` suite (no marker filtering exists yet — that's WAVE-02). Any test importing a deleted module must be found and fixed or deleted in this same wave, not left broken for WAVE-02 to discover.

### Documentation impact
`README.md` — remove any reference to Docker Compose / Celery setup instructions if present. `systems.md` — none (Celery/Scrapy were never part of the documented architecture per the exploration; confirm this remains true and note "None" explicitly in the deliverable if so).

### Acceptance criteria
- [ ] `tasks/`, `scrapers/`, `tools/selenium_driver.py`, `core/requests_client.py`, `docker-compose.yml`, `Dockerfile` no longer exist.
- [ ] `requirements.txt` no longer lists scrapy, selenium, webdriver-manager, celery, redis.
- [ ] `gpt_researcher_wrapper.py` has no Celery import or `.delay()` call.
- [ ] `web_search.py`'s dead prompt constant and dead locals are removed.
- [ ] Full existing test suite passes (or every failure is a pre-existing, documented flake unrelated to this wave).
- [ ] `core/requests_client.py`'s conventions are transcribed in the deliverable.
- [ ] `README.md` checked for stale Docker/Celery instructions; updated or confirmed clean.

### Prohibitions
Do not touch `core/router.py`, `core/agent_runtime.py`, or the `deep_research.web_search` config entry in `config/model_router.yaml` — those belong to WAVE-05 and WAVE-11 respectively. Do not add a replacement HTTP client in this wave — that is WAVE-09A.

### Agent deliverable
1. Summary of what was deleted and why (one paragraph).
2. `core/requests_client.py` conventions transcript (timeouts, retry config, pool sizes, UA string) for WAVE-09A's future reference.
3. Files changed (list).
4. Confirmation that `gpt_researcher_wrapper`'s signature is unchanged.
5. Test run output (full, not summarized).
6. Any surprises (e.g. a hidden caller found that the plan didn't know about).
7. Remaining known limitations, if any.
8. Acceptance checklist, ticked.

---

## WAVE-02 — Deterministic Test Harness and Keyless CI

### Objective
Give every subsequent wave a way to prove behavior changes without spending real API quota, and stand up continuous integration — there is currently no `.github/` directory in this repository at all.

### Dependencies
WAVE-01 (a smaller, honest dependency set makes the CI install step fast and correct). Blocks: WAVE-03 and everything downstream of it.

### Repository context
`conftest.py` already injects eight fake provider API keys into the environment and clears the LLM client cache between tests — this is the existing keyless-test convention this wave formalizes rather than replaces. `tests/test_router_fallback.py` uses `respx` to mock HTTP for OpenAI-compatible clients. `tests/test_cli_app.py:226,265` monkeypatch `cli_app.agent_chat.invoke_router` ad-hoc, per-test. The single client factory is `core/clients.py:250-266` `_openai_compat_client()` — this is the one seam a fake provider must plug into so every code path that calls `get_client()` gets the fake transparently, instead of requiring each test file to monkeypatch a different call site.

Trend-AI's equivalent: `Trend-AI/starter/backend/app/providers/content.py:55-306` `DemoContentModelProvider` (a 250-line full-fidelity, locale-aware, schema-valid demo provider) and `Trend-AI/starter/backend/tests/e2e/fake_provider.py` `DeterministicE2EProvider`, which adds **injectable failure modes** — `transient_failures`, `permanent_failure`, `delay_seconds` — so retry/timeout code paths are testable without mocking each call site individually. Trend-AI's pytest marker taxonomy (`Trend-AI/starter/backend/pyproject.toml`) is `e2e`, `real_ai` ("smoke opt-in que consume una llamada real de proveedor"), `real_trends`, `real_images`; its CI (`Trend-AI/.github/workflows/ci.yml`) runs `pytest -m "not e2e and not real_ai and not real_trends and not real_images"` and needs zero secrets.

### Scope
**In scope:**
- A `tests/fakes/` package with a `FakeLLMProvider` supporting configurable `delay_seconds`, `transient_failures` (fails N times then succeeds), and `permanent_failure` (always fails with a specified status/error shape), returning schema-valid structured responses for MultiAgent's own Pydantic output models (`TechnicalSpec`, `DebugReport`, `GroundedReport`, etc. — enumerate the ones that exist).
- Wire the fake provider through `core/clients.py`'s single factory so `get_client()` returns it when a test-mode flag/env var is set, without every test needing to monkeypatch `invoke_router` individually.
- Add a `real_ai`, `real_web`, and `e2e` pytest marker taxonomy to `pyproject.toml`.
- First `.github/workflows/ci.yml`: install deps, run `pytest -m "not e2e and not real_ai and not real_web"`, no secrets required.

**Explicitly out of scope:**
- The scenario fixture and coverage meta-test — that is WAVE-03, built on top of this wave's fake provider.
- Any change to `core/router.py`'s actual retry logic — this wave only makes it *testable*; WAVE-05 changes the logic itself.

### Mandatory inspection
`conftest.py` (full), `core/clients.py:46-266` (provider registry + factory), `tests/test_router_fallback.py` (existing respx-based pattern), `tests/test_cli_app.py:220-270` (existing ad-hoc monkeypatch pattern this wave should make obsolete for new tests, without breaking the existing ones).

### Implementation sequence
1. Design `FakeLLMProvider` matching the shape `core/clients.py` expects from a provider client (read what `_openai_compat_client()` returns and what `core/router.py` calls on it).
2. Add injectable failure/delay parameters as constructor args, not global state, so tests can configure independently without interference.
3. Wire it into `core/clients.py`'s factory behind an explicit test-mode signal (e.g. a fixture that monkeypatches `get_client`, matching the existing `conftest.py` style rather than inventing a new mechanism).
4. Add markers to `pyproject.toml`: `real_ai` (hits a live LLM provider), `real_web` (hits a live HTTP/search endpoint), `e2e` (full pipeline, may combine both).
5. Write `.github/workflows/ci.yml`: single job (or two if fast/slow split is warranted), `pip install -e .`, `pytest -m "not e2e and not real_ai and not real_web"`, no `secrets:` block required for the default job.
6. Confirm locally that the full existing suite still passes with the new fixture available (but not yet required).

### Contracts
```python
# tests/fakes/llm_provider.py
class FakeLLMProvider:
    def __init__(
        self,
        *,
        transient_failures: int = 0,
        permanent_failure: bool = False,
        delay_seconds: float = 0.0,
        responses: dict[str, Any] | None = None,  # role/schema -> canned response
    ) -> None: ...
```
Pytest markers (in `pyproject.toml`):
```toml
markers = [
  "real_ai: hits a live LLM provider, costs quota, never runs in default CI",
  "real_web: hits a live HTTP/search endpoint, never runs in default CI",
  "e2e: full pipeline run, may combine real_ai and real_web",
]
```

### Mandatory tests
A self-test of the fake provider itself: confirm `transient_failures=2` fails exactly twice then succeeds; confirm `permanent_failure=True` always fails; confirm `delay_seconds` is honored (bounded assertion, not exact timing). These tests are the wave's primary deliverable.

### Documentation impact
None in `systems.md` (it doesn't currently document testing infrastructure). Add a short "Testing" section to `README.md` if one doesn't exist, describing `pytest -m "not e2e and not real_ai and not real_web"` as the default local command.

### Acceptance criteria
- [ ] `tests/fakes/llm_provider.py` exists with the contract above.
- [ ] `core/clients.py` can return the fake provider without per-test monkeypatching of `invoke_router`.
- [ ] `pyproject.toml` has the three markers.
- [ ] `.github/workflows/ci.yml` exists, runs on push/PR, requires no secrets, and its filtered command excludes `real_ai`/`real_web`/`e2e`.
- [ ] Existing tests (`test_router_fallback.py`, `test_cli_app.py`) still pass unmodified or with only mechanical marker additions.
- [ ] Self-tests of the fake provider's failure injection pass.

### Prohibitions
Do not remove or rewrite the existing `respx`-based mocking in `test_router_fallback.py` — the fake provider is an addition, not a mandatory migration for every existing test in this wave.

### Agent deliverable
1. Summary. 2. Design decisions (why this factory seam, not another). 3. Files changed. 4. Marker taxonomy + CI file. 5. Test output (full). 6. Any provider-shape surprises found while building the fake. 7. Limitations (e.g. what the fake provider does *not* yet simulate). 8. Checklist ticked.

---

## WAVE-03 — Agent Regression Scenario Suite

### Objective
A versioned fixture of agent scenarios, backed by a meta-test that makes the fixture unable to silently rot, giving every later wave a cheap regression gate.

### Dependencies
WAVE-02 (needs the fake provider). Blocks: nothing directly, but every later wave's "no behavior regression" claim should be checkable against this suite once it exists.

### Repository context
Trend-AI's version: `Trend-AI/contracts/fixtures/ai-regression-scenarios.v1.json` — a `scenario_set_version`-stamped fixture, 30 scenarios, a matrix of 6 categories × {direct, vague, contradictory} prompt shapes. Run by `Trend-AI/starter/backend/tests/test_ai_scenarios.py`: a meta-test asserts the fixture *itself* still has the required category coverage, a minimum count, and unique IDs — "so nobody can quietly delete scenarios" — plus `@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])` for one named test per scenario. Deterministic checks (no LLM judge) live in `Trend-AI/starter/backend/app/generation/evaluation.py`, returning `(accepted, issues)`.

### Scope
**In scope:**
- `evals/scenarios.v1.json`: versioned fixture, MultiAgent-specific category matrix:
  `{vibe_coding_plan, vibe_coding_debug, deep_research_safety, deep_research_grounding, cli_tool_selection, routing_fallback}` × `{direct, vague, contradictory}` — 18 minimum cells, more than one scenario per cell encouraged.
- `tests/test_scenarios.py`: one parametrized test per scenario, using WAVE-02's fake provider, plus the coverage meta-test.
- Deterministic (non-LLM-judge) checks per category: schema validity, expected error codes, "no network was touched" (assert on a mock/spy, not on real absence of connectivity), citation presence for research scenarios.

**Explicitly out of scope:**
- Any change to the agents or graphs under test — this wave only tests, it does not fix. If a scenario reveals a real bug, record it in the deliverable's "findings" section and let a later wave (or a follow-up) fix it; do not scope-creep into a fix here.

### Mandatory inspection
`Trend-AI/contracts/fixtures/ai-regression-scenarios.v1.json` and `Trend-AI/starter/backend/tests/test_ai_scenarios.py` (the pattern to adapt, not copy verbatim — MultiAgent's schemas differ). `graphs/vibe_coding_graph.py` and `graphs/deep_research_graph.py` (the graphs being exercised). WAVE-02's `tests/fakes/llm_provider.py`.

### Implementation sequence
1. Enumerate MultiAgent's actual output schemas (`TechnicalSpec`, `DebugReport`, `GroundedReport`, `SafetyClassification`, etc. — read `schemas/deep_research.py` and equivalents) to know what "contract validity" means per category.
2. Write the fixture: at minimum one scenario per (category × prompt-shape) cell, each with `{id, category, prompt_shape, input, expected_contract}`.
3. Write the coverage meta-test first (it should fail against an empty/incomplete fixture) — this proves the guard works before scenarios are added, mirroring WAVE-06's "backfill then guard" discipline.
4. Write the parametrized scenario test, wiring each scenario's expected LLM response through the WAVE-02 fake provider's `responses` dict.
5. Write deterministic check functions per category returning `(accepted, issues)` — reuse across categories where the check is generic (schema validity), specialize where not (citation presence is research-only).

### Contracts
```json
// evals/scenarios.v1.json
{
  "scenario_set_version": "multiagent-v1",
  "scenarios": [
    {"id": "vibe_plan_direct_001", "category": "vibe_coding_plan", "prompt_shape": "direct", "input": "...", "expected_contract": {"schema": "TechnicalSpec", "error_code": null}}
  ]
}
```
```python
def check_contract(scenario, result) -> tuple[bool, list[str]]: ...  # (accepted, issues)
```

### Mandatory tests
`test_scenario_fixture_coverage()` — asserts ≥1 scenario per required category, all `{direct, vague, contradictory}` shapes represented per category, all IDs unique. `test_scenario[<id>]` — one per fixture entry, parametrized.

### Documentation impact
None in `systems.md`. Add a one-line pointer in `README.md`'s testing section (added in WAVE-02) noting the scenario suite exists and how to add a scenario.

### Acceptance criteria
- [ ] `evals/scenarios.v1.json` has ≥1 scenario per required category × shape cell.
- [ ] Coverage meta-test exists and fails if a category or shape is removed (verify this manually once, then leave it passing).
- [ ] All scenario IDs unique.
- [ ] Every scenario test passes using the fake provider, with zero live network/LLM calls.
- [ ] Deterministic checks assert on contracts (schema, error codes, citations, "no network touched"), never on model prose content.

### Prohibitions
Do not assert on exact model prose/wording anywhere in this suite — that couples the suite to a specific free-tier model's phrasing and will break on every provider swap in WAVE-06/08. Assert on structure only.

### Agent deliverable
1. Summary. 2. Category-to-schema mapping used. 3. Files changed. 4. Fixture stats (scenario count per category). 5. Test output (full). 6. Any real bugs found while building scenarios (do not fix, just record). 7. Limitations. 8. Checklist ticked.

---

## WAVE-04 — Terminal Sandbox Hardening and WSL2 Policy

### Objective
Close a real command-execution security hole and settle the Windows-support question as a documentation decision rather than a half-built native path.

### Dependencies
WAVE-02 (to test the denylist without executing real destructive commands). May run in parallel with WAVE-05 — no shared files.

### Repository context
`cli_app/tools.py:805-812` `run_terminal` calls `subprocess.run(cmd, shell=True)`. `_BLOCKED_CMD` at `cli_app/tools.py:93-98` is a **POSIX-only regex denylist** (`rm -rf /`, `sudo`, `mkfs`, `dd if=`, fork bombs, `curl|sh`). On Windows, `shell=True` invokes `cmd.exe`, where `del /f /s /q C:\` and `format` are not matched by any pattern in the denylist and pass straight through. This is a security regression specific to Windows, not merely a portability gap — it must be fixed regardless of how much native Windows support the project ultimately gets. `core/toolbox.py:834` `soft_rewrite_shell_command()` also rewrites commands to POSIX-flavored tool substitutes (`ls`→`eza`, `grep`→`rg`), which is itself POSIX-only behavior worth gating on platform.

Separately, `cli_app/env_setup.py:55` has a duplicated-literal typo: `stream.encoding.upper() not in ("UTF-8", "UTF-8")` (should presumably be `("UTF-8", "UTF8")`). Currently a no-op bug (both branches of the tuple are identical) but misleading to read.

**Known limitations to document, not fix (binding decision 3):** `bin/multiagent` + `bin/install-launcher.sh` are bash-only with a colon-separated `PYTHONPATH` (Windows needs `;`); `agents/vibe_coding/test_runner.py:217-222` `_pytest_python_candidates` only probes `venv/bin/python`/`.venv/bin/python` (Windows is `venv\Scripts\python.exe`) — note `cli_app/tools.py:302-310` `_venv_python()` **already handles both** platforms correctly, so this is an inconsistency between two functions solving the same problem, not a from-scratch gap; `core/skills.py:49` hardcodes `Path.home() / ".config" / "multiagent"` with no `%APPDATA%` awareness; `cli_app/tools.py:490` `write_text()` uses default newline translation, injecting CRLF on Windows (contrast with the atomic-write path in `graphs/vibe_coding_graph.py:304-311`, which correctly uses `newline=""`). The codebase's actual baseline is better than typical for this kind of gap: no `os.fork`, `signal.SIGKILL`, `fcntl`, `termios`, `pty`, `uvloop`, or `preexec_fn` anywhere; `cli_app/env_setup.py` already does VT100 + UTF-8 setup, and `cli_app/icons.py` has a full ASCII fallback for terminals without Unicode.

### Scope
**In scope:**
- Fix `_BLOCKED_CMD` to also cover Windows-destructive patterns (`del /f`, `format`, `rd /s`, `rmdir /s`, PowerShell `Remove-Item -Recurse -Force` on system paths) *for defense in depth*, even though the officially supported path is WSL2 (where the POSIX-only patterns already apply). Defense in depth because `shell=True` will still invoke whatever shell the host OS provides regardless of documented support status.
- Fix the `env_setup.py:55` duplicated-literal typo.
- Add a "Windows support: use WSL2" section to `README.md`, listing the known limitations above as explicit, accepted gaps (not silently undocumented).

**Explicitly out of scope:**
- Any `.ps1`/`.bat` launcher — binding decision 3.
- `%APPDATA%` migration for `core/skills.py:49` — document as a known limitation, do not fix.
- `test_runner.py:217-222` venv-path fix — document as a known limitation (note the inconsistency with `tools.py:302-310` in the writeup so a future wave can trivially fix it by copying that function, but do not do it here — out of this wave's stated scope per binding decision 3).
- `cli_app/tools.py:490` CRLF fix — same treatment.
- New CLI commands or tools — WAVE-13/14.

### Mandatory inspection
`cli_app/tools.py:80-115` (full denylist + `run_terminal`), `core/toolbox.py:800-850` (`soft_rewrite_shell_command`), `cli_app/env_setup.py` (full), `agents/vibe_coding/test_runner.py:200-230`, `cli_app/tools.py:280-320` (`_venv_python`), `core/skills.py:40-60`.

### Implementation sequence
1. Extend `_BLOCKED_CMD` with a second pattern set for Windows-shell-destructive commands; keep both active unconditionally (defense in depth costs nothing).
2. Fix the `env_setup.py:55` typo.
3. Write the README "Windows support" section: state WSL2 is the supported path, list the four known limitations verbatim with file:line references, and note the denylist fix applies regardless of platform.
4. Add tests (using WAVE-02's harness) asserting the new Windows-pattern denylist entries reject the added commands without executing them.

### Contracts
No new public contracts; `_BLOCKED_CMD`'s pattern list grows, its matching semantics (reject-if-any-pattern-matches) are unchanged.

### Mandatory tests
Parametrized test over the new denylist patterns, asserting each candidate command is rejected before `subprocess.run` is ever invoked (mock `subprocess.run` and assert it was not called for blocked inputs).

### Documentation impact
`README.md` — new "Windows support (WSL2)" section. `systems.md` — none (it doesn't currently discuss platform support).

### Acceptance criteria
- [ ] `_BLOCKED_CMD` rejects representative Windows-destructive commands (`del /f /s /q C:\`, `format C:`, `rd /s /q C:\`).
- [ ] `env_setup.py:55` typo fixed.
- [ ] `README.md` has an explicit WSL2 section listing all four known limitations with file:line refs.
- [ ] New denylist tests pass under WAVE-02's harness with zero real command execution.

### Prohibitions
No `.ps1`/`.bat` files. No `%APPDATA%` code changes. Do not fix `test_runner.py`'s venv probing or `tools.py:490`'s newline handling in this wave — document only.

### Agent deliverable
1. Summary. 2. Denylist patterns added (list). 3. Files changed. 4. README section text (quoted). 5. Test output. 6. Confirmation the typo fix is behaviorally inert (both branches were already equal). 7. Limitations documented, not fixed (list with file:line). 8. Checklist ticked.

---

## WAVE-05 — Router Reliability: Failure Taxonomy and Retry Budgets

### Objective
Replace ad-hoc, single-`max_retries` handling with a named failure taxonomy and hard per-failure-class retry budgets, and fix a real bug where the router singleton ignores its own configuration arguments after first use.

### Dependencies
WAVE-03 (needs the scenario suite + fake provider to safely change retry semantics). Blocks: WAVE-06, WAVE-07.

### Repository context
**Bug**: `core/router.py:475-487` `get_router()` caches a module-level `ModelRouter` instance and **ignores `config_path`/`quota_tracker` arguments on every call after the first** — the first caller wins forever, silently. `reset_router()` at `:490-493` is the only escape hatch, called today only from `core/agent_config.reload_config()`. This is load-bearing for any test that constructs a router with custom config on a second call within the same process — `tests/test_router_fallback.py` is the file most likely to break when this is fixed; name it explicitly in this wave's testing.

Three existing retry layers: difficulty-based pre-selection (`core/model_selector.py:293-480`, pure heuristic, no LLM, no HTTP cost); retry-with-backoff inside the router (`core/router.py:305-374`, retriable statuses `{402, 413, 422, 429}`, exponential backoff via a **blocking** `time.sleep(delay)` at `:358`, `max_retries=3`; Cohere 422 short-circuits at `:339-346` to protect its scarce ~28/day bucket; `EmptyCompletionError` — HTTP 200 with blank content — breaks straight to cascade with no retry at `:235-241`/`:323-327`); and the cascade walk (`core/router.py:396-472`, `_visited: set[(provider, model)]` cycle guard, its own `walk_guard` ring detector).

`core/agent_runtime.py:167` `run_structured_agent()` does `schema.model_validate_json(strip_fences(resp.content))` with **no retry on validation failure** at `:218` — a malformed-JSON response from a free-tier model currently either crashes or falls through to a full cascade hop, when a cheap same-model repair retry would often fix it. The only existing bespoke implementation of this idea is `agents/deep_research/synthesizer.py:156-175`, which this wave generalizes and then deletes.

### Scope
**In scope:**
- Fix `get_router()` to honor `config_path`/`quota_tracker` on every call, not just the first (or make the caching behavior explicit and documented if there's a reason to keep it — but silent ignoring is the bug, not caching per se).
- Introduce a `CallOutcome` enum/taxonomy (reserved name — binding decision 5) in `core/`, classifying: network-transient, schema-invalid, quality-rejected, quota-exhausted, rate-limited, provider-error.
- Per-class retry budgets: network-transient ≤2 with backoff (existing behavior, formalized), schema-repair exactly 1, quality-revision exactly 1 — modeled on `Trend-AI/docs/04-ai/orchestration.md`'s explicit statement: "Never silently loop indefinitely."
- Generic repair-once retry in `core/agent_runtime.py:run_structured_agent()`, feeding the Pydantic `.errors()` back to the model with a minimal-diff instruction (port of `Trend-AI/starter/backend/app/services/generate_social_post.py`'s repair pattern and `Trend-AI/starter/backend/app/providers/content.py:374-394`'s repair payload shape: `{request, invalid_output, validation_errors, instruction: "fix only what's necessary"}`).
- Delete the bespoke retry in `agents/deep_research/synthesizer.py:156-175` once the generic one covers its case.
- A body-inspecting quota classifier — port of `Trend-AI/starter/backend/app/providers/content.py:562-577` `_is_quota_exhausted()` — that checks the response body for `quota|credit|insufficient|exhausted` to distinguish a real quota wall (don't retry, don't cascade-retry either) from an ordinary retryable 429.

**Explicitly out of scope:**
- Provider registry deduplication — WAVE-06.
- Quota ledger reserve/refund semantics — WAVE-07 (this wave only produces the *classifier* WAVE-07 consumes to decide "was the provider reached").
- Making `time.sleep` non-blocking / async — noted as a finding but not fixed here; record it as a limitation if it's out of scope for this wave's session budget.

### Mandatory inspection
`core/router.py` in full, `core/model_selector.py:280-490`, `core/agent_runtime.py:150-230`, `agents/deep_research/synthesizer.py:140-180`, `tests/test_router_fallback.py` in full (this is the test file most likely to break from the singleton fix).

### Implementation sequence
1. Fix `get_router()` first, in isolation, and run `tests/test_router_fallback.py` immediately to see what breaks — this surfaces any hidden assumption about the singleton before other changes land on top.
2. Introduce `CallOutcome` and thread it through `core/router.py`'s existing retry loop, replacing ad-hoc status-code checks with taxonomy lookups where it clarifies the code (don't force it where the status-code check is already the clearest expression).
3. Add the quota-body-inspection classifier; wire it into the existing `{402,413,422,429}` handling so a body-confirmed quota-exhaustion short-circuits to cascade (like the existing Cohere 422 special case) rather than retrying.
4. Add the generic repair-once retry to `core/agent_runtime.run_structured_agent()`.
5. Migrate `synthesizer.py`'s bespoke retry to use the generic one; delete the bespoke implementation; re-run any synthesizer-specific tests.
6. Run the full WAVE-03 scenario suite and confirm no category regresses.

### Contracts
```python
# core/router.py (or a new core/call_outcome.py)
class CallOutcome(StrEnum):
    SUCCESS = "success"
    NETWORK_TRANSIENT = "network_transient"
    SCHEMA_INVALID = "schema_invalid"
    QUALITY_REJECTED = "quality_rejected"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"

RETRY_BUDGETS: dict[CallOutcome, int] = {
    CallOutcome.NETWORK_TRANSIENT: 2,
    CallOutcome.SCHEMA_INVALID: 1,
    CallOutcome.QUALITY_REJECTED: 1,
}

def get_router(config_path: Path | None = None, quota_tracker: QuotaTracker | None = None) -> ModelRouter:
    """Must honor config_path/quota_tracker on every call, not just the first."""
```

### Mandatory tests
`tests/test_router_fallback.py` — must still pass after the singleton fix (update any test that relied on the bug). New tests: repair-once retry succeeds on a schema-invalid-then-valid sequence via the fake provider; repair-once does not retry a second time on repeated failure; quota-body-classifier correctly distinguishes a quota-worded 429 from a plain rate-limit 429 using canned response bodies.

### Documentation impact
`systems.md` §4.4 ("Cómo se elige y se usa el modelo en un run") and §55-67 (quota/budget math) reference the retry behavior this wave changes — update the local facts (retry counts, the fact that schema repair now exists) in this wave; the cross-cutting recompute of §55-67's full budget math happens in WAVE-16 once WAVE-07/09B/10 also land.

### Acceptance criteria
- [ ] `get_router()` honors `config_path`/`quota_tracker` on every call.
- [ ] `tests/test_router_fallback.py` passes (updated as needed for the singleton fix, not deleted).
- [ ] `CallOutcome` enum exists in `core/` with exactly these reserved semantics (binding decision 5) — not merged with WAVE-11's `SourceResultStatus`.
- [ ] Per-class retry budgets enforced and tested (network ≤2, schema-repair exactly 1, quality exactly 1).
- [ ] `run_structured_agent()` has a generic repair-once path; `synthesizer.py`'s bespoke retry is deleted.
- [ ] Quota-body classifier distinguishes quota-exhaustion from ordinary rate-limiting in tests.
- [ ] WAVE-03 scenario suite passes with no category regression.
- [ ] `systems.md` §4.4 updated to reflect the new retry behavior.

### Prohibitions
Do not touch `core/clients.py`'s provider registry (WAVE-06) or `core/quotas.py`'s ledger (WAVE-07) beyond exposing the `CallOutcome` classifier they'll consume. Do not make `time.sleep` async in this wave — out of scope, record as a limitation.

### Agent deliverable
1. Summary. 2. Singleton bug fix explanation + what broke in `test_router_fallback.py` and how it was fixed. 3. Files changed. 4. `CallOutcome` contract. 5. Test output (full). 6. Findings (e.g. any other silent-singleton pattern found elsewhere). 7. Limitations (blocking sleep not addressed). 8. Checklist ticked.

---

## WAVE-06 — Provider Registry: Single Source of Truth

### Objective
Collapse the triple-duplicated provider list into one registry, and turn two currently-silent failure modes into loud, CI-caught ones.

### Dependencies
WAVE-05 (both touch `core/router.py`/related files; landing router reliability first avoids rebasing a taxonomy change on top of a registry refactor). Blocks: WAVE-07, WAVE-08.

### Repository context
The provider list is duplicated three ways: `core/clients.py:52` `_DEFAULT_OPENAI_COMPAT` (groq, openrouter, mistral, gemini, cerebras, ollama, agnes — all `openai_compatible`; cohere is the sole native-SDK exception, special-cased only at `core/router.py:224-233`); `core/config_editor.py:38-46` `KNOWN_PROVIDERS` (drives the `/config` TUI provider dropdown); `core/quotas.py:64-73` `_YAML_LIMIT_KEY` (maps provider → which limit key it uses) plus `core/quotas.py:76` `_PER_MODEL_PROVIDERS = frozenset({"groq"})`. `get_provider_meta()` at `core/clients.py:156-231` already merges YAML (`config/model_router.yaml`'s `providers:` block) over the builtin dict, with YAML winning — that merge order is correct and should be preserved by the new registry.

Two currently-silent failure modes, both confirmed in `config/model_router.yaml` and `core/model_selector.py`:
1. **No benchmark row → silent flat score.** `core/model_selector.py:445-448` substitutes a flat 60 for every scoring area when a provider/model has no row in `config/model_benchmarks.yaml`, making the whole difficulty-based specialization mechanism a silent no-op for that model. This should be a loud CI failure, not a quiet quality degradation.
2. **No cascade entry → dead end.** `config/model_router.yaml:171-192` `fallback_cascade:` must have an entry for every registered provider, or `core/router.py:396-422` `_next_unvisited_fallback` returns `None` and the caller gets `QuotaExhaustedError` at `:441-444` with no fallback attempted, even though other providers may have quota remaining.

### Scope
**In scope:**
- One provider registry (recommend: keep `config/model_router.yaml`'s `providers:` block as the single source, and make `core/clients.py`, `core/config_editor.py`, `core/quotas.py` all read from it instead of maintaining parallel Python-side lists — the YAML is already the canonical override layer per `get_provider_meta()`'s existing merge order).
- Two guard tests, run in CI (WAVE-02's pipeline): every provider/model referenced anywhere in `config/model_router.yaml` has a corresponding row in `config/model_benchmarks.yaml`; every provider in `config/model_router.yaml:providers:` has a corresponding entry in `fallback_cascade:`.
- Derive `conftest.py`'s fake-API-key injection list from the registry, so a new provider added later cannot silently break test collection by missing a fake key.

**Explicitly out of scope:**
- Adding any new provider (OpenCode Zen, etc.) — that's WAVE-08, which depends on this wave precisely so it becomes cheap.
- Quota reserve/refund logic — WAVE-07.

### Mandatory inspection
`core/clients.py` in full, `core/config_editor.py:30-50`, `core/quotas.py` in full, `config/model_router.yaml` in full, `config/model_benchmarks.yaml` in full, `conftest.py` (fake key injection).

### Implementation sequence
1. **Backfill first, guard second** (this is the trap flagged in Risks §1 below — do not skip this order). Before writing any guard test, check every *currently* registered provider/model against `config/model_benchmarks.yaml` and `fallback_cascade:`; add any missing rows/entries now. If the guard is written and enabled before this backfill, CI goes red on unrelated pre-existing gaps and the wave looks broken.
2. Once backfilled, write the two guard tests.
3. Refactor `core/clients.py`, `core/config_editor.py`, `core/quotas.py` to read from the single registry, preserving each module's existing external behavior/signatures exactly — this is a deduplication refactor, not a behavior change.
4. Update `conftest.py` to derive its fake-key list from the registry.
5. Run the full test suite, including WAVE-03's scenario suite, to confirm no provider-selection behavior changed.

### Contracts
```python
# core/provider_registry.py (new, or consolidated into core/clients.py)
def get_registered_providers() -> dict[str, ProviderMeta]: ...
def all_registered_models() -> list[tuple[str, str]]: ...  # (provider, model)
```
Guard tests:
```python
def test_every_model_has_benchmark_row(): ...
def test_every_provider_has_cascade_entry(): ...
```

### Mandatory tests
The two guard tests above, run as part of the default (non-`real_ai`) suite. Regression check: `core/config_editor.py`'s `/config` TUI provider list must be byte-identical in content (order may differ) before/after the refactor.

### Documentation impact
`systems.md` §3 (per-provider rate-limit research) — no content change needed unless the backfill step revealed an undocumented provider; if so, add its row. `systems.md` §4.2 (benchmark scores table) — sync if backfill added rows.

### Acceptance criteria
- [ ] Backfill completed *before* guards were enabled (state this explicitly in the deliverable, with what was added).
- [ ] Both guard tests exist, pass, and were confirmed to fail against the pre-backfill state (verify once, then leave passing).
- [ ] `core/clients.py`, `core/config_editor.py`, `core/quotas.py` read from one registry; no duplicated provider list remains in Python source.
- [ ] `conftest.py`'s fake-key injection is derived from the registry.
- [ ] Full test suite passes, including WAVE-03's scenario suite.
- [ ] `systems.md` §4.2 synced if rows were added.

### Prohibitions
Do not add any new provider in this wave (that's WAVE-08's entire reason to exist as a separate, cheap wave). Do not change `core/router.py`'s retry/cascade *logic* — only ensure its *data* (the cascade DAG) is complete.

### Agent deliverable
1. Summary. 2. Backfill list (exact rows/entries added, with justification). 3. Files changed. 4. Registry contract. 5. Test output (full, including a before/after showing the guards catch the pre-backfill gaps). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-07 — Quota Ledger: Reserve, Refund, Budgets

### Objective
Make quota accounting correct under concurrency (which WAVE-10 and WAVE-15 both introduce) and honest about calls that consumed provider-side budget without succeeding.

### Dependencies
WAVE-06 (ledger changes are cheaper once the provider list is deduplicated — a single provider-key lookup instead of `_YAML_LIMIT_KEY` + `_PER_MODEL_PROVIDERS` checked separately). Also consumes WAVE-05's quota-body classifier to decide "was the provider actually reached." Blocks: WAVE-08, WAVE-15.

### Repository context
`core/quotas.py`: SQLite at `data/quotas.db`, table `quota_usage(provider, quota_key, usage_date, call_count)` (`:112-120`), implicit daily reset via a `date.today().isoformat()` filter on every query (`:128-130`) — no cron, no background thread. `quota_key` is the model name for Groq (per-model bucket), `"__shared__"` for everyone else (`:132-142`). Thread-safe today via a `threading.Lock` + a fresh SQLite connection per operation (`:101`, `:123-125`). **Only successful calls are recorded** — `core/router.py:308`, after a successful `_dispatch`. This means a 429 that the provider counted against its own quota (common — many providers count rejected requests) is invisible to MultiAgent's own tracking, so the local ledger can drift optimistic relative to the real remaining budget.

Trend-AI's pattern (`Trend-AI/starter/backend/app/trends/quota.py` + `Trend-AI/starter/backend/app/images/budget.py`): reserve a unit **before** the call, in a transaction independent of the caller's unit of work; refund **only if the provider was never reached** (a network failure before the request left the process refunds; a 429 the provider actually processed does not); refund is addressed **by ledger row id, not by "today"** — the documented reasoning: "A job confirmed at 23:59 UTC that fails at 00:01 must return its unit to the period that took it," i.e. day-boundary crossings must not misattribute a refund to the wrong day's budget.

### Scope
**In scope:**
- Reserve-before-call: a ledger row is inserted (state `reserved`) before the HTTP request is sent, not after a successful response.
- Refund only if `CallOutcome` (WAVE-05) indicates the provider was never reached (e.g. `NETWORK_TRANSIENT` before any bytes left the process) — a call that reached the provider and got rejected (including via WAVE-05's quota-body classifier) is **not** refunded, because the provider likely counted it regardless.
- Refund by row id: the reservation row transitions `reserved → confirmed` or `reserved → refunded`, never a bare decrement against "today's count."
- Keep the existing per-provider/per-model bucket semantics (`__shared__` vs per-model) — this wave changes *when and how precisely* usage is recorded, not the bucket structure itself.
- Thread-safety audit: confirm the existing `threading.Lock` + per-operation connection pattern remains correct once WAVE-10 (concurrent fetches, which don't touch the LLM ledger directly but establish the concurrency pattern) and WAVE-15 (concurrent plan steps, which *do* make concurrent LLM calls) land.

**Explicitly out of scope:**
- Any change to *which* provider is selected (`core/model_selector.py`) — untouched here.
- New providers — WAVE-08.

### Mandatory inspection
`core/quotas.py` in full, `core/router.py:280-320` (where usage is currently recorded, at the success point), `core/quota_estimate.py` (consumes the ledger for "runs remaining today" — must not break).

### Implementation sequence
1. Add a `reserved` state to the ledger schema (migration-safe: either a new column with a default that treats existing rows as `confirmed`, or a new table — pick whichever keeps `core/quota_estimate.py`'s existing queries working with minimal changes).
2. Move the reservation insert to *before* the dispatch call in `core/router.py`.
3. After the call, transition the row based on `CallOutcome`: success → `confirmed`; provider-never-reached → `refunded` (and the row's count effectively removed from that day's total); provider-reached-but-rejected (including quota-exhausted, rate-limited, provider-error) → `confirmed` (it counts, because the provider likely counted it).
4. Update `core/quota_estimate.py`'s queries if the schema change affects them; re-verify its "runs remaining" math is still correct.
5. Add a concurrency test: fire N reservations concurrently against a shared bucket near its limit, assert the ledger never over-commits past the limit and every row ends in a terminal state (no rows stuck `reserved`).

### Contracts
```python
# core/quotas.py
class ReservationState(StrEnum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    REFUNDED = "refunded"

def reserve(provider: str, quota_key: str) -> int: ...  # returns row id
def confirm(row_id: int) -> None: ...
def refund(row_id: int) -> None: ...  # only valid from RESERVED state
```

### Mandatory tests
Concurrency test (N threads reserving against a near-exhausted shared bucket). Refund-only-if-unreached test using WAVE-05's `CallOutcome` (network-transient before dispatch → refunded; provider-rejected → confirmed, not refunded). Day-boundary test: a reservation made just before midnight that resolves just after must be attributed to the day it was reserved, not the day it resolved (mock the clock).

### Documentation impact
`systems.md` §55-67 (quota/budget math) — this wave changes what "used" means (reserved-and-not-refunded, not merely "succeeded"), which changes the math. Update the local facts here (the accounting rule); WAVE-16 recomputes the full worked examples once WAVE-08/09B/10 also land and change call counts.

### Acceptance criteria
- [ ] Reservations happen before dispatch, not after success.
- [ ] Refund only occurs when the provider was never reached (per WAVE-05's `CallOutcome`).
- [ ] Refunds/confirmations reference a row id, never "today's count."
- [ ] `core/quota_estimate.py` still produces correct "runs remaining" figures.
- [ ] Concurrency test passes: no over-commit, no stuck `reserved` rows.
- [ ] Day-boundary test passes.
- [ ] `systems.md` §55-67 accounting rule updated.

### Prohibitions
Do not change provider *selection* logic. Do not add new providers.

### Agent deliverable
1. Summary. 2. Schema migration approach and why. 3. Files changed. 4. Contract (`reserve`/`confirm`/`refund`). 5. Test output (full, including the concurrency and day-boundary tests). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-08 — Free Provider Catalog Expansion

### Objective
Add every researched free-tier provider to the catalog. With WAVE-06's registry and guards in place, this should be config-plus-benchmark-rows, CI-verified, not a Python refactor.

### Dependencies
WAVE-07 (so quota math for the new providers is sized against the corrected reserve/refund accounting, not the pre-WAVE-07 optimistic ledger).

### Repository context
Existing catalog (`config/model_router.yaml:9-108`): groq (openai-compatible, ~1000 RPD/model), openrouter (~50 RPD shared free models), mistral (Experiment tier, ~1B tokens/month), gemini (Google AI Studio free), cerebras (~1M tokens/day), ollama (local, no key), agnes (~2000 RPD shared, multimodal), cohere (native SDK, ~28/day trial).

**New — OpenCode Zen**: OpenAI-compatible base URL `https://opencode.ai/zen/v1`, no card required, signup at `opencode.ai/auth`. Free models confirmed by direct lookup: `big-pickle`, `deepseek-v4-flash-free`, `nemotron-3-ultra-free`, `mimo-v2.5-free`, `north-mini-code-free`, `laguna-s-2.1-free`, `ling-3.0-flash-free`, `hy3-free`. Per-model rate limits are **not publicly documented** — this wave must set a conservative soft `daily_limit` and note in the YAML comment that the real ceiling is unknown, matching the existing convention of documenting uncertainty in comments (see `cerebras`'s "Catalog changes often" note at `config/model_router.yaml:77-79`).

**Researched candidates** (evaluate each; add if the free tier is genuinely usable, skip with a one-line justification in the deliverable if not): NVIDIA NIM (`build.nvidia.com`, ~40 RPM, 1000 free credits — credit-based, not a clean daily-RPD model, may not fit the existing `daily_limit`/`daily_limit_shared`/`daily_limit_per_model` schema cleanly), GitHub Models (Azure-hosted OpenAI-compatible endpoint, ~10-15 RPM / 50-150 req/day, requires only a free GitHub account), Cloudflare Workers AI (~10K "neurons"/day, a non-standard unit that needs translating to an approximate request budget), Hugging Face Inference (varies by model, small free credit), Ollama Cloud (already have local Ollama; cloud variant has limited concurrent-model free tier — likely low priority given local Ollama already exists in the catalog).

### Scope
**In scope:**
- Add `opencode_zen` to `config/model_router.yaml`'s `providers:` block, matching the existing entry shape (`base_url`, `env_key`, `signup`, `notes`, `daily_limit` or `daily_limit_shared`, `models:`).
- Add benchmark rows for each opencode_zen model to `config/model_benchmarks.yaml` (WAVE-06's guard will fail CI if this is skipped).
- Add `opencode_zen_fallback:` to `fallback_cascade:` (WAVE-06's guard will fail CI if skipped) — pick a sensible fallback target given its models' apparent capability tier.
- Evaluate each researched candidate (NVIDIA NIM, GitHub Models, Cloudflare Workers AI, Hugging Face) and add the ones that fit the existing free-durable, no-card, OpenAI-compatible-preferred pattern; document why any are skipped.
- Add the new env keys to `.env.example`.

**Explicitly out of scope:**
- Assigning any new provider as a *primary* role in `vibe_coding:`/`deep_research:`/`cli:` sections — new providers land in the catalog and cascade as fallback-tier options first; promoting one to primary is a follow-up decision requiring actual usage data, not part of this wave.

### Mandatory inspection
`config/model_router.yaml` in full (the exact shape to match), `config/model_benchmarks.yaml` (scoring rubric — read §4.1 of `systems.md` for what the 0-100 areas mean before scoring new models), `.env.example`.

### Implementation sequence
1. Add `opencode_zen` provider block.
2. Add benchmark rows — score conservatively (mid-range, e.g. 50-65) for models with no established track record, and note in a YAML comment that scores are provisional pending real usage.
3. Add cascade entry.
4. Run WAVE-06's guard tests — they must pass without further changes if steps 1-3 were done correctly.
5. Evaluate each candidate provider against the existing schema (`daily_limit` / `daily_limit_shared` / `daily_limit_per_model`); for any that don't map cleanly (e.g. NVIDIA NIM's credit-based model), either approximate a daily figure with a documented assumption or skip with justification.
6. Add accepted candidates the same way as opencode_zen (steps 1-3 repeated).
7. Update `.env.example`.

### Contracts
```yaml
# config/model_router.yaml — providers:
opencode_zen:
  base_url: https://opencode.ai/zen/v1
  env_key: OPENCODE_ZEN_API_KEY
  signup: https://opencode.ai/auth
  notes: >-
    Free tier, no card required. Per-model rate limits not publicly
    documented as of this writing — daily_limit below is a conservative
    estimate, not a confirmed ceiling.
  daily_limit_shared: 100  # conservative placeholder — adjust once observed
  models:
  - big-pickle
  - deepseek-v4-flash-free
  - nemotron-3-ultra-free
  - mimo-v2.5-free
  - north-mini-code-free
  - laguna-s-2.1-free
  - ling-3.0-flash-free
  - hy3-free
```

### Mandatory tests
WAVE-06's guard tests (benchmark coverage, cascade coverage) must pass for every added provider. Add a smoke test using WAVE-02's fake provider confirming `get_client("opencode_zen")` resolves without error.

### Documentation impact
`systems.md` §3 — add a `### 3.9 OpenCode Zen` (and further subsections for any accepted candidates) following the existing per-provider subsection format. §4.2 — sync new benchmark rows.

### Acceptance criteria
- [ ] `opencode_zen` fully registered (provider, benchmarks, cascade) and WAVE-06's guards pass.
- [ ] Each researched candidate has an explicit accept-and-add or reject-with-justification decision recorded.
- [ ] `.env.example` updated with new env keys.
- [ ] `systems.md` §3 and §4.2 updated.
- [ ] No new provider promoted to a primary role — catalog/fallback tier only.

### Prohibitions
Do not promote any new provider to primary in `vibe_coding:`/`deep_research:`/`cli:`. Do not skip the benchmark/cascade steps and rely on WAVE-06's guards to "catch it later" — do it right the first time; the guards are a safety net, not a to-do list.

### Agent deliverable
1. Summary. 2. Provider-by-provider accept/reject table with justification. 3. Files changed. 4. New YAML blocks (quoted). 5. Test output (full, including WAVE-06 guards). 6. Findings (e.g. rate limits discovered empirically vs. documented). 7. Limitations (unconfirmed rate limits, credit-based providers approximated). 8. Checklist ticked.

---

## WAVE-09A — HTTP Cache Core (standalone, unwired)

### Objective
Build and unit-test a single-flight HTTP response cache in isolation. Nothing in the research pipeline is modified in this wave — the cache module exists and is proven correct, but unused, until WAVE-09B wires it in.

### Dependencies
WAVE-03 (needs the scenario suite / fake infrastructure pattern established, even though this wave doesn't touch LLM calls — for consistent testing conventions). Blocks: WAVE-09B.

### Repository context
No HTTP response cache exists anywhere in the repo today. The same URL is commonly fetched 3-4× within one research run: once as a primary source, once as a DuckDuckGo result page, once by `verify_cited_urls` during grounding, once again during synthesis. `core/requests_client.py` (deleted in WAVE-01) had no caching either — WAVE-01's deliverable transcribed its timeout/retry/UA conventions for this wave to reuse where relevant, but the caching logic itself is new.

Trend-AI's reference implementation, `Trend-AI/starter/backend/app/trends/cache.py` (227 lines, asyncio-based — MultiAgent's equivalent must be **threaded**, matching the existing `ThreadPoolExecutor` idiom already used at `agents/deep_research/source_fetch.py:942` and `:1372`, not asyncio):
- `cache_key(source, adapter_version, region, category, query, public_parameters)` joins fields with `\x1f` and SHA-256 hashes them. **`adapter_version` is part of the key** — changing the HTML parser auto-invalidates every cached entry from before the change, with no manual cache-bust needed.
- Values over 64KB (`MAX_CACHE_VALUE_BYTES`) are refused, not stored.
- **Reads re-validate**: `_decode` runs the stored value back through validation before returning it, so a corrupted or poisoned cache entry cannot inject bad data into a live run.
- `coalesce(key, fetch, operation_deadline_seconds)` provides single-flight behavior: concurrent requests for the same key share one in-flight fetch rather than each issuing a duplicate HTTP request. The lock dict is refcounted and popped at zero — "do not retain one local lock per historical cache key forever."
- **Negative caching**: an `EMPTY` result (source responded but had nothing) is cached with a *shorter* TTL than a normal hit, so a persistently-empty source doesn't get re-hit every call, but a transiently-empty one recovers reasonably fast.

### Scope
**In scope:**
- `core/http_cache.py` (new module): `cache_key()`, `get()`/`put()` with the 64KB size guard, re-validate-on-read, `coalesce()` single-flight with a threading-lock-based (not asyncio) implementation, negative caching for empty results, refcounted lock cleanup.
- Full unit test coverage of the cache module in isolation — no dependency on `source_fetch.py` or any live/mocked HTTP call.

**Explicitly out of scope:**
- Wiring this into `fetch_url()` or any research code — that is WAVE-09B, deliberately separated because "cache module + re-validate-on-read + single-flight + negative-caching + fetch_url integration + verify_cited_urls sharing" in one wave is too large for one session (this exact split was recommended precisely to avoid that).
- Deciding cache backend persistence (in-memory vs. SQLite vs. disk) beyond what's needed for correctness within a single process run — if a wave-scoped decision is needed, default to in-memory (a dict, thread-safe) since MultiAgent is a CLI process that starts fresh each invocation, and note this decision explicitly rather than over-engineering persistence nobody asked for.

### Mandatory inspection
`Trend-AI/starter/backend/app/trends/cache.py` (the pattern — read in full, do not port asyncio idioms literally), `agents/deep_research/source_fetch.py:942` and `:1372` (the existing `ThreadPoolExecutor` idiom this module must be consistent with), WAVE-01's deliverable (transcribed `requests_client.py` conventions, for timeout/retry defaults if relevant to what gets cached).

### Implementation sequence
1. Design `cache_key()` — decide what "adapter_version" means for MultiAgent (likely a version string for the HTML-extraction logic in `source_fetch.py`, bumped whenever `html_to_text`/`extract_structured_signals` changes materially — WAVE-09B will supply the actual version string when it wires this in; this wave just needs the parameter to exist).
2. Implement the size guard and re-validate-on-read `get()`/`put()`.
3. Implement `coalesce()` using `threading.Lock` per key, a refcounted dict of locks, cleanup at zero.
4. Implement negative caching (shorter TTL constant for empty results, exposed as a parameter, not hardcoded, so WAVE-09B can tune it).
5. Write unit tests covering: cache hit/miss, size-guard rejection, re-validation catching a corrupted stored value, single-flight coalescing under concurrent access (spin up N threads requesting the same key, assert the underlying fetch function is called exactly once), negative-TTL expiring faster than positive-TTL.

### Contracts
```python
# core/http_cache.py
def cache_key(source: str, adapter_version: str, **params: str) -> str: ...

class HttpCache:
    def get(self, key: str) -> CacheEntry | None: ...  # re-validates on read
    def put(self, key: str, value: bytes, *, ttl_seconds: float, negative: bool = False) -> None: ...
    def coalesce(self, key: str, fetch: Callable[[], T], deadline_seconds: float) -> T: ...
```

### Mandatory tests
As listed in Implementation sequence step 5 — all in-process, no network, no LLM, run under the default (non-marked) suite.

### Documentation impact
None — this module isn't referenced by anything yet, so nothing in `systems.md` is falsified by its mere existence.

### Acceptance criteria
- [ ] `core/http_cache.py` implements all four contract functions.
- [ ] Size guard rejects oversized values.
- [ ] Re-validation catches a deliberately-corrupted stored entry in a test.
- [ ] `coalesce()` proven single-flight under concurrent access (fetch called exactly once for N concurrent requesters).
- [ ] Negative-TTL is shorter than positive-TTL and is configurable, not hardcoded.
- [ ] Zero references to this module from `agents/deep_research/` or `core/search_guards.py` (confirms it's truly unwired, per scope).

### Prohibitions
Do not import or reference this module from `source_fetch.py` or `search_guards.py` in this wave — that coupling is WAVE-09B's entire purpose and doing it early defeats the split.

### Agent deliverable
1. Summary. 2. Design decisions (in-memory vs. persistent, TTL defaults chosen and why). 3. Files changed. 4. Contract. 5. Test output (full, including the concurrency single-flight proof). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-09B — Wire the Cache Into the Fetch Chokepoint

### Objective
Route every HTTP read in the research pipeline through WAVE-09A's cache, eliminating the 3-4× duplicate-fetch pattern.

### Dependencies
WAVE-09A. Blocks: WAVE-10 (parallelizing before caching is actively harmful — see Risks §1; this ordering is non-negotiable).

### Repository context
All HTTP is stdlib `urllib.request` — no `requests`, no `httpx`, no async. The chokepoint every fetch path funnels through is `agents/deep_research/source_fetch.py:1267` `fetch_url()`: `urllib.request.Request` + `urlopen(timeout=...)`, reads `max(max_chars*3, 200_000)` bytes, decodes UTF-8 with `errors="replace"`. HTML→text is a hand-rolled `HTMLParser` subclass `_HTMLToText` at `:257-290` — **deliberately not BeautifulSoup**; `agents/vibe_coding/web_quality.py:141-146` actively lints against introducing bs4, so this wave must not add it either, even transitively via a new dependency.

`core/search_guards.py:270-308` `verify_cited_urls` is called **twice** per research run on overlapping URL sets: once from `agents/deep_research/grounding.py:166` and again from `agents/deep_research/synthesizer.py:205`. With the cache wired in, the second call becomes free (cache hits) instead of re-fetching.

### Scope
**In scope:**
- `fetch_url()` gains cache-aware behavior: check `HttpCache.get()` first (using a cache key derived from URL + relevant fetch parameters + an `adapter_version` string bumped whenever `html_to_text`/`extract_structured_signals` change), fall through to the real `urlopen()` on miss, `put()` the result (respecting the 64KB guard and negative-caching for empty bodies) before returning.
- `core/search_guards.verify_cited_urls` automatically benefits once `fetch_url()` is cache-aware underneath it — no separate cache-wiring needed there, confirm this with a test showing the second call (from `synthesizer.py`) hits cache for URLs already fetched during `grounding.py`'s call.
- Single-flight coalescing applied at `fetch_url()`'s level so concurrent callers (once WAVE-10 adds concurrency) requesting the same URL share one fetch.

**Explicitly out of scope:**
- Adding concurrency itself — WAVE-10. This wave only makes concurrency *safe* to add next.
- Any parser/extraction logic change — the `adapter_version` string is introduced here as a cache-invalidation hook, but the extraction logic itself (`_HTMLToText`, `extract_structured_signals`) is untouched.
- BeautifulSoup or any other HTML parsing library — prohibited, matches the existing lint rule.

### Mandatory inspection
`agents/deep_research/source_fetch.py:1267-1340` (`fetch_url` in full), `core/search_guards.py:260-310` (`verify_cited_urls`), `agents/deep_research/grounding.py:160-175`, `agents/deep_research/synthesizer.py:195-215`, `agents/vibe_coding/web_quality.py:135-150` (the bs4 lint rule this wave must not violate).

### Implementation sequence
1. Define the `adapter_version` string as a module-level constant in `source_fetch.py`, documented as "bump this when `_HTMLToText` or `extract_structured_signals` changes materially."
2. Wrap `fetch_url()`'s body: cache lookup → on miss, existing `urlopen` logic unchanged → cache `put()` before returning, respecting size guard and negative-caching for the existing "empty body after extract" branch (`:1313-1321`).
3. Wrap the whole thing in `HttpCache.coalesce()` so this wave is concurrency-safe even before WAVE-10 lands.
4. Write a test proving the grounding→synthesizer double-fetch scenario now hits cache on the second call (mock the underlying `urlopen`, assert it's called once for a URL fetched by both `grounding.py` and `synthesizer.py` in one run).
5. Confirm zero new dependency was added (no bs4, no requests, no httpx).

### Contracts
`fetch_url()`'s public signature and `FetchedSource` return type are **unchanged** — this is a transparent caching layer, not an API change. Internal addition:
```python
_ADAPTER_VERSION = "source-fetch-v1"  # bump on material extraction-logic changes
```

### Mandatory tests
The grounding→synthesizer cache-hit test above. A cache-miss-then-hit test for a single `fetch_url()` call repeated twice. A negative-cache test (empty body cached with shorter TTL, re-fetched sooner than a normal hit would be). Full WAVE-03 scenario suite re-run to confirm no research-category regression.

### Documentation impact
`systems.md` §2 ("Calls per pipeline — budget math") — the call-count assumptions there predate caching; note the change locally (this wave's fetch-count reduction), full recompute in WAVE-16 once WAVE-10 also lands and further changes the numbers.

### Acceptance criteria
- [ ] `fetch_url()` is cache-aware; `FetchedSource` and the function signature are unchanged externally.
- [ ] `verify_cited_urls`'s second call (synthesizer after grounding) demonstrably hits cache for shared URLs.
- [ ] No bs4 or other new HTML-parsing dependency introduced.
- [ ] `coalesce()` is in place (even though nothing concurrent calls it yet — this wave makes WAVE-10 safe).
- [ ] WAVE-03 scenario suite passes with no regression.
- [ ] `systems.md` §2 updated with the local fetch-count change.

### Prohibitions
No BeautifulSoup, no `requests`/`httpx` dependency, no concurrency changes (WAVE-10's job), no extraction-logic changes beyond the `adapter_version` cache-bust hook.

### Agent deliverable
1. Summary. 2. Cache-key design for `fetch_url()` (what parameters go in, why). 3. Files changed. 4. Confirmation of unchanged public contract. 5. Test output (full, including the grounding→synthesizer hit-rate proof). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-10 — Concurrent Fetching

### Objective
The single highest-ROI latency fix in the repository: parallelize the three serial HTTP loops, now that WAVE-09B makes doing so safe rather than harmful.

### Dependencies
WAVE-09B (mandatory — see Risks §1; parallelizing before single-flight caching converts a serial duplicate-fetch problem into a simultaneous thundering-herd problem, which is worse). Blocks: WAVE-11.

### Repository context
Three serial loops, all confirmed by direct read:
- `agents/deep_research/source_fetch.py:1697-1706` — `fetch_search_documents` runs `search_duckduckgo(q)` **serially per facet**, up to `MAX_FACET_HINTS=12` facets (`web_search.py:84`), each a blocking `urlopen(timeout=12.0)` — worst case ≈144s just for search.
- `agents/deep_research/source_fetch.py:1716-1730` — then fetches up to `max_fetches=8` result pages **serially**, `timeout=12.0` each — worst case +96s.
- `core/search_guards.py:300-308` `verify_cited_urls` loops `for url in to_check: fetch_url(...)` — up to `max_verify=8`, `timeout=6.0`, **serial** — +48s. Called twice per run (grounding + synthesizer), but WAVE-09B already made the second call cache-cheap; this wave's concurrency win applies to the first (cold) call.

The pattern already exists in the same file — `fetch_user_primary_sources` (`:1372`) and `fetch_outbound_presence_pages` (`:942`) both already use `ThreadPoolExecutor(max_workers=min(3, n))`. This wave extends the same pattern to the three loops above; it does not invent a new concurrency primitive.

### Scope
**In scope:**
- Parallelize `fetch_search_documents`'s per-facet DuckDuckGo search loop with `ThreadPoolExecutor`, worker count matching the existing convention (`min(3, n)` or similar — stay consistent with the two existing call sites rather than picking an arbitrary new number).
- Parallelize the up-to-8 result-page fetch loop the same way.
- Parallelize `verify_cited_urls`'s per-URL check loop the same way.
- Preserve existing timeout values (`12.0`, `6.0`) per-request; concurrency reduces wall-clock, not per-request timeout budget.

**Explicitly out of scope:**
- Any change to *what* is searched or fetched — that's WAVE-11.
- Rendering (Lightpanda) — WAVE-12.

### Mandatory inspection
`agents/deep_research/source_fetch.py:940-980` and `:1370-1400` (the two existing `ThreadPoolExecutor` call sites — match their style exactly), `:1680-1740` (the two loops to parallelize), `core/search_guards.py:260-310`.

### Implementation sequence
1. Parallelize `verify_cited_urls` first — smallest, most isolated change, good smoke test for the pattern in this codebase post-09B.
2. Parallelize the result-page fetch loop (`:1716-1730`).
3. Parallelize the per-facet search loop (`:1697-1706`) — largest worst-case win, do it last so the pattern is already proven twice.
4. Measure and record wall-clock improvement on a representative scenario from WAVE-03's suite (using the fake provider's `delay_seconds` to simulate realistic latency, since real network calls aren't available in default CI).

### Contracts
No public signature changes — `fetch_search_documents`, `verify_cited_urls` keep their existing return shapes; only their internal execution strategy changes from serial to parallel.

### Mandatory tests
A timing-bound test (not exact-timing, bounded — e.g. "N parallel fake fetches with `delay_seconds=1` each complete in under 2×`delay_seconds` total, not N×`delay_seconds`") for each of the three parallelized loops, using WAVE-02's fake provider's configurable delay. Confirm result ordering/content is unaffected by parallelization (order-independent aggregation, or explicit re-sorting if order matters downstream).

### Documentation impact
`systems.md` §2 (budget math) — record the latency improvement locally; WAVE-16 folds it into the full recompute.

### Acceptance criteria
- [ ] All three loops use `ThreadPoolExecutor` consistent with the existing two call sites' worker-count convention.
- [ ] Per-request timeouts unchanged.
- [ ] Timing-bound tests pass for all three loops.
- [ ] Result content/ordering is unaffected by the change (explicit test).
- [ ] WAVE-03 scenario suite passes with no regression.
- [ ] `systems.md` §2 updated with the measured improvement.

### Prohibitions
Do not change what is searched, how many facets/results are requested, or timeout values — this wave is purely execution-strategy, not policy.

### Agent deliverable
1. Summary. 2. Before/after worst-case latency estimate (with the timing-bound test's actual numbers). 3. Files changed. 4. Confirmation of unchanged public contracts. 5. Test output (full). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-11 — Search Resilience and Source Status Contracts

### Objective
Remove the single point of failure in web search, replace boolean success/fail with an honest status taxonomy, and resolve the ambiguous fate of the never-invoked `deep_research.web_search` role.

**Note on size:** this wave is marked **L** in the wave index. If, after step 1 of the implementation sequence, the role-fate decision is "wire it" (multi-engine search + query expansion), split into **WAVE-11A** (status contracts + partial validation + scoring, no new engine) and **WAVE-11B** (multi-engine wiring), landing 11A first. If the decision is "reclaim the RPD," the wave stays single-session.

### Dependencies
WAVE-10 (multi-engine search, if pursued, needs the executor pattern already in place — running N engines serially would make latency worse, not better). Blocks: WAVE-12.

### Repository context
The only real search engine in the product is a **DuckDuckGo lite HTML scrape**: `agents/deep_research/source_fetch.py:1592-1677` `search_duckduckgo()`, hitting `https://lite.duckduckgo.com/lite/?q=...` with a spoofed Chrome UA, regex-parsing the results table (`_parse_ddg_results`, `:1599-1630`, with a secondary fallback regex at `:1620-1629` — both fragile). One DDG markup change silently drops every facet's results to zero, degrading the whole pipeline to primary-source-only with no visible error.

The `deep_research.web_search` role is fully configured — `groq/compound-mini`, ~250 RPD reserved (`config/model_router.yaml:152-154`), listed in `core/config_editor.KNOWN_ROLES`, scored in `config/model_benchmarks.yaml`, counted by `core/quota_estimate.py` — but **`run_web_search()` makes zero LLM calls**. The docstrings at `web_search.py:4` and `core/clients.py:17` still claim otherwise. This wave must resolve this, not merely note it again (WAVE-01 already removed the dead prompt constant inside the function; this wave decides the config-level question).

### Scope
**In scope:**
- Port `Trend-AI/starter/backend/app/trends/contracts.py`'s pattern: a `SourceResultStatus` enum (reserved name, binding decision 5) with 7 values — `SUCCESS, EMPTY, TIMEOUT, ERROR, INVALID, RATE_LIMITED, QUOTA_EXHAUSTED` — replacing the current boolean `ok` field on `FetchedSource` and DDG search results. `source_applies()`-equivalent logic: a source outside its declared scope is `NOT_APPLICABLE`, not a failure, and must not count against health metrics.
- Partial validation: when a batch of search results contains some malformed entries, drop the bad ones individually and keep the good ones, rather than discarding the whole batch.
- Port `Trend-AI/starter/backend/app/trends/scoring.py`'s pattern: versioned, decomposed scoring — `SCORING_VERSION` constant, explicit weights, return `(components, total)` so a ranking is inspectable/explainable in CLI output, not just a single opaque number.
- **Decide the `deep_research.web_search` role's fate**, explicitly, as a first implementation step (see below) — this is not optional and not deferrable to a later wave.

**Explicitly out of scope:**
- Concurrency mechanics — already landed in WAVE-10; this wave changes *what* is fetched/scored, not *how many at once*.
- Lightpanda — WAVE-12, which depends on this wave's status contracts to represent "rendered but empty" distinctly from "fetch failed."

### Mandatory inspection
`agents/deep_research/source_fetch.py:1580-1740` (full search + fetch chain), `agents/deep_research/web_search.py` (full, post-WAVE-01 cleanup), `config/model_router.yaml:137-154` (`deep_research:` role block, specifically `web_search:`), `core/quota_estimate.py` (references the role), `core/config_editor.py` (`KNOWN_ROLES`).

### Implementation sequence
1. **First, decide the `web_search` role's fate.** Two options, pick one and justify in the deliverable:
   - **(a) Reclaim the RPD**: remove the `deep_research.web_search` role entirely from `config/model_router.yaml`, `KNOWN_ROLES`, and the benchmark table; update `core/quota_estimate.py` to stop counting it; correct the docstrings at `web_search.py:4` and `core/clients.py:17`. Simpler, ships faster, frees ~250 RPD of Groq quota for roles that actually use it.
   - **(b) Wire it**: use the role's LLM call for query expansion (turn a vague user topic into better DDG search facets) or cross-engine result re-ranking. This is the "L, may need to split into 11A/11B" path — requires designing an actual prompt and validating it earns its RPD cost against WAVE-03's scenario suite.
   - Either decision must leave zero ambiguity: no config entry that's "maybe" used.
2. Introduce `SourceResultStatus` and thread it through `FetchedSource` and DDG search results, replacing the boolean `ok` field (update all call sites that currently check `.ok`).
3. Add partial validation to the DDG result parser (`_parse_ddg_results`) — malformed individual results are dropped, not the whole page.
4. Add versioned decomposed scoring for ranking search results (if not already present in some form — check before assuming greenfield).
5. If (1) was "wire it," implement the query-expansion/re-ranking call using the concurrency pattern from WAVE-10, and validate it against WAVE-03's `routing_fallback`/research categories before considering the wave complete.

### Contracts
```python
# agents/deep_research/source_fetch.py (or a shared contracts module)
class SourceResultStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    ERROR = "error"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    NOT_APPLICABLE = "not_applicable"

SCORING_VERSION = "search-v1"
def score_result(result) -> tuple[dict[str, float], float]: ...  # (components, total)
```

### Mandatory tests
DDG-markup-change resilience: feed `_parse_ddg_results` a deliberately malformed page fragment, assert `INVALID`/partial-drop behavior rather than a silent empty return. Status-taxonomy test: every call site previously checking `.ok` now checks the correct `SourceResultStatus` value. If (1)(b) was chosen: a WAVE-03 scenario proving query expansion measurably improves a vague-prompt research scenario's outcome.

### Documentation impact
`systems.md` §0 (role inventory) — flip `deep_research.web_search`'s status to reflect the decision made in step 1. §6 (System B role assignments) — same. If reclaimed, note the freed RPD; if wired, document the new prompt/behavior.

### Acceptance criteria
- [ ] The `web_search` role's fate is decided and implemented — no ambiguous "reserved but unused" state remains.
- [ ] `SourceResultStatus` (7+ values, reserved name per binding decision 5) replaces boolean `ok` throughout the search/fetch chain.
- [ ] Partial validation: a batch with some bad entries keeps the good ones.
- [ ] Versioned decomposed scoring in place, `(components, total)` shape.
- [ ] DDG-markup-resilience test passes.
- [ ] WAVE-03 scenario suite passes with no regression (and, if wiring web_search, shows measurable improvement on the relevant scenario).
- [ ] `systems.md` §0 and §6 updated with the role decision.

### Prohibitions
Do not merge `SourceResultStatus` with WAVE-05's `CallOutcome` — separate types per binding decision 5. Do not leave the role decision unresolved.

### Agent deliverable
1. Summary. 2. **The web_search role decision, with justification** (this is the wave's most important output). 3. Files changed. 4. `SourceResultStatus` contract + call-site migration list. 5. Test output (full). 6. Findings. 7. Limitations (whether the wave was split into 11A/11B, and why). 8. Checklist ticked.

---

## WAVE-12 — Optional Lightpanda Rendering

### Objective
Close the JS-rendering gap in social-profile and SPA fetching, without adding a hard dependency — MultiAgent is a free-tier CLI tool and must work identically for a user who never installs Lightpanda.

### Dependencies
WAVE-11 (needs `SourceResultStatus` to represent "rendered but still empty" distinctly from "fetch failed," and needs the wave's fetch chain to already be cache-aware and concurrent so rendering slots into a stable interface).

### Repository context
There is **no JS rendering anywhere on the live path** today. `fetch_outbound_presence_pages` (`agents/deep_research/source_fetch.py:883-971`) fetches social profile pages that are commonly SPA shells or behind login walls, and the code **already acknowledges** this returns near-empty text at `:892`. [Lightpanda](https://github.com/lightpanda-io/browser) is an open-source headless browser written in Zig: DOM/JS(V8)/XHR/Fetch/cookies/click-events support, exposes a **Chrome DevTools Protocol (CDP)-compatible** endpoint — meaning existing Playwright/Puppeteer scripts point at it via `browserWSEndpoint` with zero code changes — and benchmarks at ~11x faster / ~9x less memory than headless Chrome because it does no graphical rendering, fonts, or layout, operating purely on DOM/JS/CDP.

The clean insertion point is the single chokepoint every fetch path already funnels through: `fetch_url()` at `source_fetch.py:1267` (confirmed unchanged in location by WAVE-09B, which only added caching around it, not a new call path).

### Scope
**In scope:**
- A `render: Literal["none", "lightpanda"] = "none"` parameter on `fetch_url()`.
- When `render="lightpanda"`: connect to a Lightpanda instance over CDP (via websocket) and drive it to load the URL, wait for a reasonable settle condition, extract the rendered DOM's text — **no Playwright/Puppeteer Python dependency**; speak CDP directly over the websocket, or shell out to the `lightpanda` binary if that's the more robust integration path (evaluate both, document the choice).
- Graceful degradation: if the Lightpanda binary/endpoint is not available (default case for nearly every user), `render="lightpanda"` requests silently fall back to `render="none"` behavior with exactly one log line — never an exception, never a hang.
- `render` becomes part of WAVE-09A's cache key (a rendered and unrendered fetch of the same URL are different cache entries — they can produce materially different text).
- Callers most likely to benefit (`fetch_outbound_presence_pages`) get an opt-in `render="lightpanda"` path, but the default for the rest of the fetch chain stays `"none"`.

**Explicitly out of scope:**
- Making Lightpanda a required dependency, bundling a binary, or auto-installing it — explicitly prohibited; this must ship as a no-op for the default install.
- Any change to which pages get fetched — WAVE-11's domain.

### Mandatory inspection
`agents/deep_research/source_fetch.py:883-971` (`fetch_outbound_presence_pages`, the primary intended caller), `:1267-1340` (`fetch_url`, the integration point), WAVE-09A's `core/http_cache.py` (cache-key contract to extend), WAVE-11's `SourceResultStatus` (to represent a Lightpanda fetch that succeeded technically but rendered empty content, distinct from a fetch that failed to connect to Lightpanda at all).

### Implementation sequence
1. Evaluate CDP-over-websocket vs. shelling out to the `lightpanda` binary; pick one, document why in the deliverable.
2. Implement the connection/render/extract path behind the `render` parameter, with a hard timeout distinct from (likely longer than) the plain-fetch timeout, since rendering is slower than a raw GET.
3. Implement the absence-detection: probe for the Lightpanda endpoint/binary once (cache the probe result for the process lifetime, don't re-probe per call), fall back silently to `"none"` if absent.
4. Extend the WAVE-09A cache key to include `render`.
5. Wire `fetch_outbound_presence_pages` to opt into `render="lightpanda"`.
6. Write the mandatory no-op test: run the fetch chain with no Lightpanda binary present (the default test environment) and assert behavior is byte-identical to pre-WAVE-12.

### Contracts
```python
# agents/deep_research/source_fetch.py
def fetch_url(
    url: str,
    *,
    timeout: float = 18.0,
    max_chars: int = 12000,
    user_agent: str = _DEFAULT_UA,
    extract_signals: bool = True,
    follow_outbound: bool = True,
    render: Literal["none", "lightpanda"] = "none",
) -> FetchedSource: ...
```

### Mandatory tests
**The no-op test is the most important test in this wave**: full research pipeline run, Lightpanda absent, assert zero behavior change vs. the pre-WAVE-12 baseline. A rendering test gated behind a `real_web`-equivalent marker (or skipped entirely in CI if no Lightpanda binary is available in the CI image — do not make CI depend on installing Lightpanda). Cache-key test: `render="none"` and `render="lightpanda"` fetches of the same URL produce distinct cache entries.

### Documentation impact
`systems.md` — add a short note (likely a new subsection near §3 or a new numbered section) describing Lightpanda as an optional, off-by-default capability, how to enable it, and the explicit guarantee that its absence changes nothing.

### Acceptance criteria
- [ ] `render` parameter added to `fetch_url()`, default `"none"`.
- [ ] No Playwright/Puppeteer Python dependency added.
- [ ] Absence of the Lightpanda binary/endpoint degrades silently to identical pre-WAVE-12 behavior (proven by the no-op test).
- [ ] `render` is part of the cache key.
- [ ] `fetch_outbound_presence_pages` opts into rendering.
- [ ] `systems.md` documents the capability as optional and off-by-default.

### Prohibitions
No hard dependency on Lightpanda. No bundling/auto-install of the binary. No exception raised when the binary is absent — log and degrade only.

### Agent deliverable
1. Summary. 2. CDP-vs-binary integration decision and why. 3. Files changed. 4. Contract (the `render` parameter). 5. Test output (full, with the no-op test's output highlighted). 6. Findings. 7. Limitations (e.g. what settle-condition heuristic was used for "page loaded"). 8. Checklist ticked.

---

## WAVE-13 — CLI Surface and Agent-Loop Hygiene

### Objective
Make the pipelines directly scriptable from the outer CLI (today they're TUI-only), fix a tool that silently returns garbage, and remove leftover debug code from the agent chat loop.

### Dependencies
WAVE-03 (needs the harness to safely change chat-loop behavior). Blocks: WAVE-14, and (cross-track) contributes to WAVE-15's dependency chain.

### Repository context
`cli.py` (click, entry point `multiagent = cli:main`) exposes: `quota`, `history`, `config{show,set,reset}`, `keys{status,set}`, `providers`, `chat`, `skills{list,add,enable,disable,remove,show}`, `tools{doctor,suggest,search,show,list,alt,profiles}`. **Pipelines are not outer commands** — `/do` (the pipeline-invoking slash command) exists only inside the TUI's chat loop (`cli_app/commands.py:410-499`, full slash-command registry at `:903-930`). This makes MultiAgent unusable in a non-interactive/scripted context (CI, cron, another program's subprocess call) without going through the TUI.

`cli_app/tools.py:767-786` — the agent-callable `webfetch` tool uses raw `urllib.request` with **no HTML→text conversion at all**, returning raw decoded bytes truncated to length. `html_to_text` already exists (in `source_fetch.py`, and per WAVE-09B, now cache-aware) but `webfetch` doesn't use it.

Read-only tools execute **one at a time** in the approval loop (`cli_app/agent_chat.py:336-349`) even though `cli_app/tools.py:128-129`'s help text tells the model "Read tools may be batched" — the model is told a capability the host doesn't honor. `MAX_ROUNDS = 8` at `cli_app/agent_chat.py:30`.

Two hardcoded host-side intercepts run **before the LLM ever sees the turn**: a graph-refresh check (`:151-165`) and a "hola mundo" special case (`:169-222`, matched by `_HELLO_RE` at `:38`, which writes a literal `hola_mundo.py` file) — this reads as leftover debug/demo code, not a documented feature. **Trap**: `tests/test_cli_app.py:267` calls `commands.chat_turn("hola", s)` — bare "hola" does not match `hola\s*mundo`, so removing the intercept should not break this specific test, but re-run it explicitly to confirm rather than assuming.

### Scope
**In scope:**
- Add outer `cli.py` commands (or a `pipeline`/`run` subcommand group) that invoke `/do`'s underlying `plan_pipelines()` → `execute_plan()` flow (`cli_app/orchestrate.py:163`) directly, without requiring the TUI.
- Fix `webfetch` to route through `html_to_text` (reusing WAVE-09B's cache-aware `fetch_url` if it fits the tool's existing timeout/size semantics — check before assuming a drop-in swap).
- Batch read-only tool execution in the approval loop so it matches what the model is already told.
- Delete the "hola mundo" intercept and its regex/handler.
- Keep the graph-refresh intercept unless investigation shows it's also dead/leftover — verify its purpose before removing (it may be legitimate session-state maintenance, unlike the hola-mundo case).

**Explicitly out of scope:**
- New tools beyond fixing `webfetch` — WAVE-14.
- Windows-specific sandbox changes — WAVE-04 already landed those.
- Concurrent plan-step execution — WAVE-15.

### Mandatory inspection
`cli.py` in full, `cli_app/commands.py:400-500` and `:900-930`, `cli_app/orchestrate.py:150-270`, `cli_app/tools.py:120-135` and `:760-790`, `cli_app/agent_chat.py:140-230` and `:330-350`, `tests/test_cli_app.py:220-270`.

### Implementation sequence
1. Investigate the graph-refresh intercept's purpose (read surrounding code/tests/commits if available) before deciding its fate; document the finding either way.
2. Delete the "hola mundo" intercept; run `tests/test_cli_app.py:267` explicitly and confirm it still passes.
3. Fix `webfetch` to produce readable text via `html_to_text`.
4. Batch read-only tool execution: change the approval loop to execute all read-only tools in a batch when the model requests multiple in one turn, while keeping write tools strictly one-at-a-time (per existing safety design — do not weaken write-tool approval).
5. Add outer CLI pipeline command(s), wired to the existing `plan_pipelines()`/`execute_plan()` functions — no new orchestration logic, just a new entry point to existing logic.
6. Re-run the full test suite plus WAVE-03's scenario suite.

### Contracts
```
multiagent pipeline run "<task description>" [--gpt|--native]
```
maps to the same `plan_pipelines()` → `execute_plan()` flow `/do` already uses inside the TUI — no new pipeline logic, just a non-TUI entry point.

`webfetch` tool's output format changes from raw truncated bytes to `html_to_text`-processed text — document this as a behavior change for any downstream consumer/test expecting the old raw format.

### Mandatory tests
`tests/test_cli_app.py:267` re-confirmed passing after the hola-mundo deletion. New test: `webfetch` on a representative HTML fixture returns readable text, not raw markup. New test: read-only tool batching — model requests 3 read tools in one turn, all 3 execute without 3 separate approval round-trips (write tools remain one-at-a-time in the same test). New test: the outer `pipeline run` command produces the same result as the equivalent `/do` TUI invocation, using the fake provider.

### Documentation impact
`systems.md` §7 (CLI roles) — document the new outer pipeline command. `README.md` — add the new command to usage examples.

### Acceptance criteria
- [ ] Outer CLI can invoke a pipeline without the TUI.
- [ ] `webfetch` returns `html_to_text`-processed content.
- [ ] Read-only tools batch in the approval loop; write tools remain one-at-a-time.
- [ ] "Hola mundo" intercept deleted; graph-refresh intercept's fate is a documented decision (kept or removed, with reasoning).
- [ ] `tests/test_cli_app.py:267` passes.
- [ ] New tests (webfetch text quality, batching, CLI/TUI parity) pass.
- [ ] `systems.md` §7 and `README.md` updated.

### Prohibitions
Do not weaken write-tool (mutating) approval — it must remain strictly one-at-a-time regardless of the read-tool batching change. Do not remove the graph-refresh intercept without first confirming its purpose.

### Agent deliverable
1. Summary. 2. Graph-refresh intercept investigation finding + decision. 3. Files changed. 4. New CLI command contract. 5. Test output (full, `test_cli_app.py:267` explicitly called out). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-14 — New Agent Tools

### Objective
Expand the agent-callable tool surface, strictly within the existing READ/WRITE approval taxonomy.

### Dependencies
WAVE-13 (CLI/loop hygiene should land first so new tools are added to a clean loop, not one still carrying the hola-mundo intercept or unbatched reads). Also depends on WAVE-04 (new tools that touch the terminal must inherit the hardened denylist).

### Repository context
`cli_app/tools.py`: READ tools (no approval required, `:39-52`) = `graphify_query`, `list_dir`/`list`, `read_file`/`read`, `grep`, `glob`, `webfetch`, `toolbox_query`/`toolbox`. WRITE tools (approval required, `:54-67`) = `write_file`/`write`, `edit_file`/`edit`, `apply_patch`, `run_terminal`/`bash`, `graphify_update`, `create_venv`, `pip_install`. All paths resolve under `work_root()` (the launch cwd, not the install tree, `:26-35`), with escape checks and a secret-file blocklist (`_safe_under_root`, `:267-285`). Toolbox catalog `config/cli_toolbox.yaml` (1113 lines), loaded via `core/toolbox.py:133-176`, agent-facing entry point `query_for_agent(q, mode=suggest|doctor|search|show|alt|runtime)` at `:541`.

The user's request names "tools for the CLI" generically — this wave's job is to propose and implement a small, well-justified set, not to maximize tool count. Candidates worth considering (evaluate, don't blindly implement all): a `git_diff`/`git_log` READ tool (agents currently have no structured way to inspect git history, only `run_terminal` which requires approval for a read-only operation); a `run_tests` READ-adjacent tool that runs the project's test suite and returns structured pass/fail (currently only reachable via `run_terminal`, forcing an approval prompt for a non-mutating action); a `search_web` tool that surfaces WAVE-11's search chain to the general chat agent (today, DDG search is only reachable inside the Deep Research pipeline, not the free-form chat tool loop).

### Scope
**In scope:**
- Evaluate the candidate tools above (and any others found to have clear precedent/need); implement the ones that clearly reduce unnecessary approval friction for read-only operations or fill a clear capability gap.
- Every new tool is explicitly classified READ or WRITE and added to the correct list in `cli_app/tools.py`.
- Every new tool that shells out inherits WAVE-04's hardened `run_terminal` path rather than calling `subprocess` directly.
- Update `tools_help_text()` (or equivalent) so the model is told about new tools accurately — avoid repeating WAVE-13's "told a capability the host doesn't honor" mistake.

**Explicitly out of scope:**
- Any tool that could mutate state without going through the existing WRITE-tool approval flow — no exceptions.
- Redesigning the approval UI itself.

### Mandatory inspection
`cli_app/tools.py` in full (especially `:39-115` for the READ/WRITE lists and denylist, and `:760-820` for existing tool implementations to match style), `config/cli_toolbox.yaml` structure, `core/toolbox.py:530-560` (`query_for_agent`).

### Implementation sequence
1. Finalize the tool list to implement (candidates above, pruned to what's clearly justified) and record the decision with reasoning in the deliverable.
2. Implement each tool matching the existing style of `cli_app/tools.py`'s other implementations (parsing conventions, error shapes, path-safety reuse via `_safe_under_root`).
3. Classify each into READ or WRITE explicitly; add to the correct constant list.
4. Update the model-facing help text.
5. Add each new tool to WAVE-03's scenario suite's `cli_tool_selection` category (at least one scenario exercising each new tool).

### Contracts
Each new tool follows the existing tool-call shape (parsed via `parse_tool_calls`, `cli_app/tools.py:210-251`) — no new dispatch mechanism.

### Mandatory tests
One test per new tool confirming correct READ/WRITE classification and approval behavior (READ tools execute without an approval round-trip in the test harness; WRITE tools require one). WAVE-03 scenario suite extended and passing.

### Documentation impact
`systems.md` — if it documents the tool list anywhere (check §7/CLI roles section, extended by WAVE-13), add the new tools there too.

### Acceptance criteria
- [ ] New tool list finalized with documented reasoning (why these, not others).
- [ ] Every new tool correctly classified READ or WRITE.
- [ ] Any tool that shells out uses WAVE-04's hardened path.
- [ ] Model-facing help text accurately describes new tool capabilities.
- [ ] WAVE-03 scenario suite extended with at least one scenario per new tool.
- [ ] `systems.md` updated if applicable.

### Prohibitions
No tool bypasses the READ/WRITE approval taxonomy. No tool calls `subprocess` directly instead of going through the hardened terminal path.

### Agent deliverable
1. Summary. 2. Tool selection reasoning (what was considered, what was implemented, what was rejected and why). 3. Files changed. 4. Per-tool contract + classification. 5. Test output (full). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-15 — Orchestration Research and Concurrent Plan Execution

### Objective
Produce a short decision record comparing orchestration approaches, then land the one concurrency improvement it justifies: parallel execution of independent plan steps.

### Dependencies
**WAVE-07 (cross-track — do not skip this).** Concurrent plan steps make concurrent LLM calls; the quota ledger must already be reserve-before-call and thread-safe, or concurrent steps will over-spend a free-tier daily budget and corrupt `data/quotas.db` accounting under race conditions. Also depends on WAVE-13 (CLI surface should be stable first, since this wave changes what happens inside the pipeline execution WAVE-13 exposed).

### Repository context
`cli_app/orchestrate.py:180-262` runs multi-step plans in a plain sequential `for` loop. Steps marked `uses_prior=False` (i.e. don't depend on a prior step's output) are, by the plan's own data model, independent — and currently still run one after another.

The user asked for research into "orchestration tooling" generally. This wave's research output should evaluate, at minimum: **LangGraph-native parallel branches** (MultiAgent already depends on LangGraph for both System A and System B graphs — using its native fan-out/fan-in support for independent plan steps would be the most architecturally consistent choice) versus **a plain `ThreadPoolExecutor`** in `orchestrate.py` directly (simpler, consistent with the pattern already used throughout `agents/deep_research/source_fetch.py`, but sidesteps LangGraph's own state-management guarantees for this one code path). The research output is a short ADR, recorded in this wave's deliverable — not a separate standalone document, to keep the roadmap's file count minimal.

### Scope
**In scope:**
- A short ADR (in the deliverable, not a new file) comparing LangGraph-native parallel branches vs. thread-pool-in-orchestrate.py, with a recommendation.
- Implement the recommended approach for `orchestrate.py:180-262`'s independent (`uses_prior=False`) steps.
- Ensure every concurrent LLM call goes through WAVE-07's reserve-before-call ledger correctly under concurrency (this is the acceptance-critical part — a plan that "parallelizes" but silently races the quota ledger is worse than the sequential version).

**Explicitly out of scope:**
- Rewriting System A or System B's own internal graphs to be parallel — architect→coder→debugger and safety_filter→...→synthesizer remain intentionally sequential (each step's output feeds the next); this wave only concerns the *outer* plan-step loop in `orchestrate.py`, which is a different, coarser level of orchestration.
- Any provider/routing change — already handled by Tracks A.

### Mandatory inspection
`cli_app/orchestrate.py` in full, WAVE-07's `core/quotas.py` reserve/refund contract, `graphs/vibe_coding_graph.py:911-953` and `graphs/deep_research_graph.py:520-550` (to confirm — not to change — that the *inner* graphs stay sequential; this wave must not accidentally touch them).

### Implementation sequence
1. Write the ADR first, before implementing — read both options' tradeoffs against MultiAgent's actual constraints (free-tier quota, LangGraph already a dependency, existing thread-pool convention elsewhere in the codebase) and commit to a recommendation.
2. Implement: identify independent steps (`uses_prior=False`) in a plan, execute them concurrently via the chosen mechanism, gather results, continue the sequential chain for dependent steps.
3. Stress-test against WAVE-07's ledger: run a plan with several independent steps that together approach a shared provider's daily limit, confirm the ledger correctly serializes/reserves without over-commit (this reuses WAVE-07's concurrency test pattern).
4. Confirm System A/B's internal graphs are untouched — this is a "did not touch" acceptance criterion, not just an absence of complaints.

### Contracts
No change to the plan data model (`uses_prior` already exists and is the signal this wave consumes). `execute_plan()`'s external return shape is unchanged; only its internal execution strategy for independent steps changes.

### Mandatory tests
The quota-ledger stress test above (concurrent independent steps near a shared limit, using WAVE-07's test pattern). A correctness test: a plan with a mix of independent and dependent steps produces the same final result under concurrent execution as it did under the old sequential execution (using the fake provider for determinism).

### Documentation impact
`systems.md` — if orchestration/planning is documented (check the CLI/roles sections extended by WAVE-13), note that independent plan steps now execute concurrently.

### Acceptance criteria
- [ ] ADR recorded in the deliverable with a clear recommendation and reasoning.
- [ ] Independent (`uses_prior=False`) plan steps execute concurrently.
- [ ] Dependent steps remain sequential, in order.
- [ ] Quota ledger stress test passes (no over-commit under concurrent plan-step execution).
- [ ] Correctness test: concurrent execution produces the same result as sequential did, for a mixed plan.
- [ ] System A/B's internal LangGraph node sequences are confirmed unchanged.
- [ ] `systems.md` updated if applicable.

### Prohibitions
Do not parallelize System A's architect→coder→debugger chain or System B's safety_filter→...→synthesizer chain — those are genuinely sequential (each step needs the prior's output) and out of scope. Do not implement concurrent plan execution without the WAVE-07 ledger stress test passing first.

### Agent deliverable
1. Summary. 2. **The ADR** (LangGraph-native vs. thread-pool, with recommendation and reasoning). 3. Files changed. 4. Contract (unchanged `execute_plan()` shape). 5. Test output (full, ledger stress test highlighted). 6. Findings. 7. Limitations. 8. Checklist ticked.

---

## WAVE-16 — Documentation Coherence Pass

### Objective
The cross-cutting `systems.md`/`README.md` rewrite no single wave can do correctly, because it depends on facts only settled once every other wave has landed.

### Dependencies
All prior waves (01-15).

### Repository context
Every prior wave already performed **local** documentation repair (per `## How to execute a wave` rule 4) — adding a provider row, flipping a role's status, updating a local budget figure. What remains is **global coherence**: sections whose correctness depends on the combined effect of multiple waves.

`systems.md` (594 lines) sections most affected:
- **§0** (role inventory) — reconcile against WAVE-11's `web_search` decision, WAVE-06's registry cleanup, WAVE-08's new providers.
- **§3** (per-provider rate limits) — should already have OpenCode Zen (and any accepted candidates) from WAVE-08; verify completeness and consistent formatting across all subsections.
- **§4.2** (benchmark scores table) — verify every provider/model from WAVE-06's guard-enforced backfill and WAVE-08's additions is represented.
- **§8** (fallback cascade DAG) — redraw the full DAG diagram; it changed shape across WAVE-06 (dedup), WAVE-07 (reserve/refund doesn't change the DAG shape but changes what "exhausted" means), and WAVE-08 (new providers added as fallback-tier nodes).
- **§55-67-ish** (quota/budget math, "Calls per pipeline") — full recomputation: WAVE-09B's caching changes call counts, WAVE-10's concurrency changes wall-clock (not call count), WAVE-07's reserve/refund changes what counts as "used," WAVE-11's web_search decision changes role-level RPD reservations.

`README.md` — verify the "Testing" section (WAVE-02), "Windows support (WSL2)" section (WAVE-04), and any new CLI usage examples (WAVE-13) are all present and mutually consistent.

### Scope
**In scope:**
- Full read-through of `systems.md` against the current state of the codebase (not against what each wave's local patch claimed — verify against actual code, since local patches from 15 different waves may have small inconsistencies).
- Redraw §8's fallback DAG to match the post-WAVE-08 provider/cascade reality.
- Recompute §2/§55-67's budget math from scratch against the current call-count and caching reality.
- Reconcile §0's role inventory against every role-affecting decision made across the roadmap.
- Cross-check `README.md` against `systems.md` for consistency (e.g. the same provider list, same command examples).

**Explicitly out of scope:**
- Any code change. This wave is documentation-only. If it discovers a code/doc mismatch that isn't a doc bug (i.e. the code itself regressed a promise made by an earlier wave), record it as a finding for follow-up, do not fix it inline.

### Mandatory inspection
`systems.md` in full (594 lines — read all of it, not a subset). `README.md` in full. Every prior wave's `Documentation impact` section in this roadmap, as a checklist of what should already be locally correct (verify, don't trust blindly).

### Implementation sequence
1. Read `systems.md` end to end against current code, noting every stale fact.
2. Redraw §8's DAG.
3. Recompute §2/budget-math sections with current numbers (post-caching call counts, current provider list).
4. Reconcile §0's role inventory.
5. Verify §3/§4.2 completeness (every registered provider/model represented).
6. Cross-check `README.md` against the updated `systems.md`.
7. Produce a short "what changed and why" summary at the top of the diff (not necessarily in the file itself) for the deliverable.

### Contracts
None — documentation only.

### Mandatory tests
None new. Re-run the full test suite (including WAVE-03's scenario suite and WAVE-02's CI filter) as a final confirmation that the roadmap's implementation is complete and stable — this is the natural point to confirm the whole roadmap, not just the docs, is in a good state.

### Documentation impact
This wave *is* the documentation impact. `systems.md` and `README.md` fully reconciled.

### Acceptance criteria
- [ ] `systems.md` §0, §2/budget math, §3, §4.2, §8 all verified against current code, not against stale wave-local claims.
- [ ] §8's DAG diagram matches the actual `fallback_cascade:` config.
- [ ] Budget math in §2/§55-67-region recomputed with current numbers.
- [ ] `README.md` cross-checked for consistency with `systems.md`.
- [ ] Full test suite (default filter) passes.
- [ ] Any discovered code-level regression (not a doc bug) is recorded as a finding, not silently fixed.

### Prohibitions
No code changes in this wave.

### Agent deliverable
1. Summary of what was stale and what was fixed. 2. Section-by-section diff summary for `systems.md`. 3. Files changed (docs only). 4. N/A (no contracts). 5. Final full-suite test output. 6. Any code-level findings requiring follow-up. 7. Limitations. 8. Checklist ticked.

---

## WAVE-17 — Structured CLI Output and Cross-AI Context

### Objective
Two user-driven goals: (1) implement the researched structured CLI output proposal (envelope with `status`/`message`/`timestamp`/`detail`/`errorCode`, global `--json` mode, POSIX stdout/stderr split, exit codes, signal handling) end-to-end; (2) close the two context gaps between chat and the two orchestration systems — the planner AIs currently never see the chat conversation, and the chat AI neither knows about the two systems' work nor can invoke them.

### Dependencies
WAVE-13 (CLI surface + `pipeline run` headless), WAVE-15 (`execute_plan` shape), WAVE-16 (docs baseline).

### Repository context
- `CommandResult {ok, text, data}` (`cli_app/commands.py:38`) has an underused `data` slot; `chat_turn` returns a plain dict; `ToolResult {name, ok, output, skipped}` (`cli_app/tools.py:126`) — no timestamps, no error codes anywhere; errors are freeform strings ("Planner failed (...): ...").
- The outer CLI (`cli.py`) prints via `click.echo/secho` mixed streams; `pipeline run` echoes progress to stdout (`cli.py:643`), violating the "results→stdout, diagnostics→stderr" rule.
- Planner context (`_build_planner_context`, `commands.py:373`) is project files + graphify only; `plan_pipelines(..., context=...)` (`agents/planner.py:63`) has no chat-history input. `pipeline_cli.run_pipeline` (headless, `pipeline_cli.py:35`) has no context param at all.
- Chat seed (`_seed_context`, `agent_chat.py:43`) re-queries the knowledge graph every turn unconditionally and knows nothing about pipeline runs (`core/runs.py` history) or the two systems beyond one line in the system prompt.
- No tests assert outer-CLI text output (no CliRunner tests), so changing the non-JSON text is low risk.

### Scope
**In scope:**
1. New `cli_app/output.py`: envelope schema (`status` OK/WARNING/ERROR, `message`, `timestamp` UTC ISO 8601, `detail` container, `errorCode`, optional `context`), dual renderers (human block / JSON, same info), `MAE-` error-code catalog with Explanation/Action, POSIX exit-code mapping (0 OK / 1 ERROR / 2 usage), SIGINT/SIGTERM handler for headless (structured final message, exit 130), `eprint()` (diagnostics→stderr), and `emit()` that respects a `--json` flag.
2. `cli.py`: global `--json` flag on the `main` group; **every** subcommand (`history`, `quota`, `config`, `keys`, `providers`, `skills`, `tools`, `pipeline run`, chat preflight) emits a structured envelope (JSON in `--json` mode, current-style block text otherwise). `pipeline run --json`: stdout = final envelope only, progress → stderr, exit 0/1. Preflight messages → stderr.
3. Envelope fields on `CommandResult` (optional `status`/`error_code`/`timestamp`), `chat_turn` return dict (same, additive), `ToolResult` (`timestamp`, `error_code`; approval rejection → `MAE-3xxx`). TUI keeps reading `.text`/`.data` — no break.
4. **Planner receives chat context**: new `_chat_context_for_planner(session)` building a `=== CHAT HISTORY ===` block from recent turns, merged into the planner `context` in `/do`; `pipeline_cli.run_pipeline` gains `chat_context=""` param; planner system prompt acknowledges the block.
5. **Chat receives the two systems' context + a `run_pipeline` tool**: briefing block in `_system_prompt` and `session.system_prompt`; `=== RECENT PIPELINE RUNS ===` injected in `_seed_context` from `get_run_history().list_recent(limit=4)`; new `run_pipeline` tool in `cli_app/tools.py` (WRITE_TOOLS → approval), delegating to `pipeline_cli.run_pipeline` with optional session/chat-context + progress via an optional `ctx` param on `run_tools`/`exec_tool` supplied by `agent_chat`.
6. **Chat context audit fixes**: (a) gate the per-turn graph re-query on graph.json mtime, reusing `session.cached_graph_snippet` when unchanged (same policy as the planner via `should_use_graphify`); (b) dynamic recent-message count (up to 8) when usage ratio is low; (c) new `llm_compact` CLI setting (default off) that switches auto-compaction from local-drop to `compact_with_llm`; document the rest of the audit as-is.

**Explicitly out of scope:**
- Changing the TUI visual chrome beyond what flows through `CommandResult`/`chat_turn` shapes.
- Reintroducing `/vibe` / `/research` as direct commands (deliberately removed; the `run_pipeline` chat tool covers the chat-side need, not the slash-command surface).
- Any changes to `agents/planner.py` plan schema, `execute_plan` return shape, or pipeline graphs.

### Mandatory inspection
`cli.py` (full, 653 lines), `cli_app/commands.py` handlers + dispatch, `cli_app/tools.py` (tool catalog, `exec_tool`, `run_tools`, `format_tool_results`), `cli_app/agent_chat.py` (full), `cli_app/pipeline_cli.py` (full), `cli_app/session.py`, `core/runs.py` (`RunHistory`), `agents/planner.py` (`plan_pipelines`), `cli_app/context_tools.py` (`should_use_graphify`), TUI result handling (`tui.py` `_handle_result`).

### Implementation sequence
1. `cli_app/output.py` + unit tests for renderers/exit codes.
2. `cli.py` global `--json` + per-command envelopes + stderr routing + signal handler (headless paths only).
3. `CommandResult`/`chat_turn`/`ToolResult` envelope fields + errorCode assignments at failure sites.
4. Planner chat-context: `_chat_context_for_planner` + merge in `/do` + `run_pipeline(chat_context=...)`.
5. Chat: briefing + recent-runs seed + `run_pipeline` tool (with `ctx` plumbing) + help text.
6. Chat audit fixes (mtime gating, dynamic recent count, `llm_compact`).
7. `tests/test_wave17.py`; full default suite; docs (`systems.md` CLI output contract + context wiring; `README.md` flags/tool).

### Contracts
- `run_pipeline(task, *, use_gpt_researcher=False, provider=None, model=None, progress=None, chat_context="") -> dict` — return dict gains `status`, `timestamp`, `error_code`, `detail` keys; existing `ok`/`text`/`plan`/`steps` keys preserved (tests `test_wave13.py:52-86` depend on them).
- `run_tools(calls, *, approve=None, always_approve=False, one_mutating_at_a_time=True, ctx=None)` — `ctx` optional; absent for all existing callers.
- `exec_tool(name, args, *, ctx=None)` — only `run_pipeline` consumes `ctx`.
- `CommandResult` — `status`/`error_code`/`timestamp` optional dataclass fields with defaults; `ok` maps to `status` when `status` not set.
- `ToolResult` — `timestamp`/`error_code` optional fields with defaults.
- Global `--json` accepted on every subcommand; affects only the printed envelope, never stored state.

### Mandatory tests
New `tests/test_wave17.py`: envelope JSON validity + field presence; block renderer contains status/message; errorCode → exit code; `history --json` / `pipeline run --json` via Click `CliRunner` (ok → exit 0, error → exit 1, stdout parses as JSON, no progress on stdout); planner receives CHAT HISTORY (spy on `plan_pipelines` kwargs from `/do`); `run_pipeline` tool runs with fake pipeline + approval, is in `WRITE_TOOLS`; chat seed includes RECENT PIPELINE RUNS when runs exist; graph mtime gating (query call count unchanged when graph.json mtime stable, requery on change). Plus: full default suite stays green.

### Documentation impact
`systems.md`: new "CLI output contract" subsection (§10-ish, next to anti-patterns): envelope fields, `MAE-` error-code catalog, `--json` behavior, stdout/stderr policy, exit codes, signal handling; chat/planner context wiring facts (planner now sees CHAT HISTORY; chat sees RECENT PIPELINE RUNS + `run_pipeline` tool; graph re-query mtime policy; `llm_compact` default off). `README.md`: `--json` usage on commands, `run_pipeline` chat tool entry, context flow one-liner.

### Acceptance criteria
- [ ] `cli.py` has a global `--json` flag; every subcommand emits a structured envelope; `pipeline run --json` stdout is JSON-only with progress on stderr; exit codes 0/1 (+130 on SIGINT).
- [ ] `CommandResult`/`chat_turn`/`ToolResult` carry `status`/`error_code`/`timestamp`; all existing failure sites have an errorCode; no existing key removed.
- [ ] `/do` passes a CHAT HISTORY block to `plan_pipelines`; `run_pipeline` accepts `chat_context`; planner system prompt recognizes it.
- [ ] Chat system prompt briefs the two systems; seed includes RECENT PIPELINE RUNS; `run_pipeline` tool exists in the catalog, requires approval, and passes chat context to the planner.
- [ ] Chat graph re-query is mtime-gated; recent-message count is dynamic; `llm_compact` setting exists (default off).
- [ ] `tests/test_wave17.py` passes; full default suite passes.
- [ ] `systems.md` + `README.md` updated with the above facts.

### Prohibitions
No changes to the pipeline graphs or `execute_plan` return shape. No removal of existing `CommandResult`/`chat_turn`/`ToolResult` fields (additive only). No `/vibe`/`/research` slash-command reintroduction.

### Agent deliverable
1. Summary. 2. Research basis for the output schema (IBM DS8000 message format + metasintaxis CLI Output Spec) and how it maps to MultiAgent. 3. Files changed. 4. Contract changes + test output (full default suite + new wave tests). 5. Error-code catalog table. 6. Findings/limitations. 7. Checklist ticked.

---

## WAVE-18 — Role Consolidation via Stronger Prompts

### Objective
Cut LLM calls per pipeline by removing roles whose work can be absorbed into a neighboring role's system prompt, without weakening the anti-hallucination / merge-safety guarantees. User-selected scope: (1) fold the `safety_filter` role into `context_compressor` (System B); (2) fold the `architect` role into `coder` (System A); (3) upgrade the `debugger` prompt with full file context; (4) let the `debugger` fix code directly via an optional `fixed_files` payload (hybrid editor, fallback to coder when absent). Measured on real `runs.db` mix (12 vibe runs: 1×attempts=1, 4×2, 7×3): System A avg 6.0 → ~4.4 calls/run (**-27%**), System B 5 → 4 (**-20%**); combined **~-22%**.

### Dependencies
WAVE-15 (`execute_plan` consumes only `is_safe`/`content`/`sources` keys — preserved), WAVE-17 (envelope conventions; no graph changes allowed by WAVE-17's prohibitions are re-opened).

### Repository context
- System A currently: `architect_node` → `coder_node` → `test_executor_node` → `debugger_node` (loop). Calls = 1 + 2×fix_attempts. Architect's output (`TechnicalSpec`) is consumed verbatim by the coder; its only host-side use is `read_existing_sources` pre-read for merge context (`vibe_coding_graph.py:364`).
- System B currently: `safety_filter_node` (dedicated `gpt-oss-safeguard-20b` call) → `context_compressor_node` → `web_search` → `grounding` → `synthesizer`. `SafetyClassification` and `CondensedTrends` are separate schemas; `_SAFETY_HARD` regex already exists (`difficulty_scorer.py:137`).
- Debugger sees 4000-char file previews (`debugger.py:66-70`) — suspects for mis-diagnosis given 58% of real runs reach attempts=3.
- Quota math source of truth: `core/quota_estimate.py:_DEFAULT_SYSTEM_SPECS` (vibe 3 roles / research 5 roles). Role registry: `core/config_editor.py:KNOWN_ROLES`. Per-role benchmarks/effort: `config/model_benchmarks.yaml`.

### Scope
**In scope:**
1. **System A — architect folded into coder**: delete `agents/vibe_coding/architect.py`; extend `CodeArtifact` with optional `architecture`/`test_cases`/`files_to_create`; coder prompt = architect planning rules + coder merge rules (surgical file list, grounded facts, static-site rules, landing quality); coder receives the repo tree (paths only, `git ls-files`-style, capped) since pre-read of existing files is impossible pre-call; post-call `read_existing_sources` on `artifact.files_to_create` feeds the existing preservation-warning diff; graph entry → `coder`.
2. **System A — debugger as hybrid editor**: `DebugReport.fixed_files: Optional[dict[str,str]]`; debugger prompt: full corrected files when confident and fully readable, else `suggested_fix`; preview cap 4000 → 12000 chars, `test_logs` cap → 20000; new `fix_applier` node (path validation like `_write_artifact_files`, updates `artifact` state) routed from debugger → `test_executor`; suggested_fix path unchanged (→ `coder`).
3. **System B — safety folded into context_compressor**: extend `CondensedTrends` with `is_safe: bool = True` + `safety_reasons: list[str] = []`; compressor prompt gains a safety-gate section (same categories as the old safety prompt); host-side hard pre-gate on the existing `_SAFETY_HARD` regex; delete `safety_filter_node` + `agents/deep_research/safety_filter.py`; graph entry → `context_compressor`; routing on `trends.is_safe`; summarize keeps emitting `is_safe`/`safety_reasons` keys (consumers `cli_app/commands.py:625`, `orchestrate.py:113-114`, `test_planner.py`, `test_wave15.py` depend on them).
4. **Config + quota**: remove `architect` + `safety_filter` role blocks from `config/model_router.yaml`, `config/defaults_model_router.yaml`, per-role rows + `role_effort` entries in `config/model_benchmarks.yaml`; `KNOWN_ROLES`; `_DEFAULT_SYSTEM_SPECS` (vibe = coder+debugger = 2, research = compressor+web_search+grounding+synthesizer = 4).

**Explicitly out of scope:**
- Merging `grounding`+`synthesizer` (double-pass scrub/verify is the anti-hallucination core) — analyzed and rejected, see documentation impact.
- Removing the optional `web_search` query-expansion LLM call (user declined).
- Changing `execute_plan` return shape or the `is_safe`/`sources` summary keys.

### Mandatory inspection
`graphs/vibe_coding_graph.py` (full), `graphs/deep_research_graph.py` (full), `agents/vibe_coding/architect.py`, `agents/vibe_coding/coder.py`, `agents/vibe_coding/debugger.py`, `agents/deep_research/context_compressor.py`, `agents/deep_research/safety_filter.py`, `schemas/vibe_coding.py`, `schemas/deep_research.py`, `core/quota_estimate.py`, `core/config_editor.py`, `core/reasoning_params.py`, `config/model_benchmarks.yaml`, `tests/test_graphs_mocked.py`, `tests/test_quota_estimate.py`, `tests/test_handoff.py`, `tests/test_model_selector.py`, `tests/test_reasoning_params.py`, `tests/test_cli_app.py`, `tests/test_wave05_retry.py`.

### Implementation sequence
1. Schemas first (additive fields + defaults, so existing callers keep working).
2. System A: coder rewrite + graph fold + debugger prompt/preview + `fix_applier` + routing.
3. System B: compressor safety gate + graph fold + summarize keys preserved.
4. Config/quota/benchmarks cleanup (`KNOWN_ROLES`, specs, YAML, role_effort).
5. Tests: update `test_graphs_mocked` (vibe: no architect, fix-applier path; research: compressor gates, no safety calls), `test_quota_estimate` (2/4 calls, fixtures drop removed roles), `test_model_selector`/`test_reasoning_params` (architect/safety paths → coder/compressor), `test_cli_app` role listings; new tests: `fixed_files` path skips coder, unsafe query aborts at compressor (regex pre-gate + LLM gate), preservation warning still fires post-fold.
6. Docs: `systems.md` §2 budget math (new call counts + % improvement table), §5 (merged flow), §6 (safety gate in compressor), §4.3 role table, status line; `README.md` "Vibe coding"/"Default roles" sections.
7. Full default suite; commit spec + implementation as separate commits.

### Contracts
- `run_coder(task_text, *, repo_tree="", router_instance=None, assessment=None, selection_out=None, **kwargs) -> CodeArtifact` — signature change (was `spec: TechnicalSpec`).
- `CodeArtifact` — additive optional `architecture`/`test_cases`/`files_to_create`; existing `files`/`summary` required.
- `DebugReport` — additive optional `fixed_files`; `passed`/`issues`/`suggested_fix` unchanged.
- `CondensedTrends` — additive `is_safe`/`safety_reasons` with safe defaults.
- Graph handoff names: vibe `coder` → `test_executor` → `debugger` → (`fix_applier`|`coder`|`git_commit`|`git_rollback`); research `context_compressor` → (`END` unsafe | `web_search` → …).
- Summaries: `invoke_vibe_coding_pipeline`/`invoke_deep_research_pipeline` return keys unchanged.

### Mandatory tests
New: `fixed_files` short-circuits coder (debugger provides files → coder call count 0 on the fix cycle, tests re-run); `fixed_files=None` keeps coder loop; unsafe query aborts at compressor (no grounding/synth calls) and regex pre-gate aborts on hard signals; vibe preservation warning fires with merged coder; quota `pipeline_role_calls` = 2 (A) / 4 (B). Updated: graph mocked tests (call counts, handoff chains, state keys), quota estimate tests (fixtures drop architect/safety_filter), `test_model_selector`/`test_reasoning_params` role paths, `test_cli_app` role listings. Full default suite stays green.

### Documentation impact
`systems.md`: §2 calls-per-pipeline table (A: 2-5→2-4, B: 5-6→4-5 with the optional web expansion), new "WAVE-18 role consolidation" subsection with the % improvement table (A -17% guaranteed / -27% with editor debugger, B -20%, combined ~-22%, happy path -33%) and the rejected grounding+synthesizer merge rationale; §5 role table without architect; §6 role table without safety_filter (compressor gains safety gate); §4.3 benchmark role table; status line. `README.md`: vibe flow line ("Architect → Coder" → merged implementer), "Default roles" table.

### Acceptance criteria
- [ ] `architect` and `safety_filter` roles removed from YAML, defaults, benchmarks, `KNOWN_ROLES`, quota specs; no code path references them.
- [ ] System A happy path = 2 LLM calls (implementer + debugger); fix loop with `fixed_files` = 1 call/cycle; `suggested_fix` fallback keeps the coder loop.
- [ ] System B = 4 LLM calls (compressor w/ safety gate, web_search optional expansion, grounding, synthesizer); unsafe topics abort before search; summary keys `is_safe`/`safety_reasons` preserved.
- [ ] Preservation warnings + landing-quality rules still enforced after the architect fold; debugger preview cap raised.
- [ ] `tests` updated + new wave tests pass; full default suite green.
- [ ] `systems.md` + `README.md` updated with call counts, role tables, and % improvement.

### Prohibitions
No changes to `execute_plan`/`pipeline_cli` return shapes, `is_safe`/`sources` summary keys, or the `grounding`/`synthesizer` two-pass design. No reintroduction of `/vibe`/`/research` slash commands. Do not touch `Trend-AI/` or `graphify-out/`.

### Agent deliverable
1. Summary. 2. Role-consolidation analysis with % improvement per candidate (real runs.db mix) and rejected-option rationale. 3. Files changed. 4. Contract changes + test output. 5. Findings/limitations. 6. Checklist ticked.

---

## Risks and sequencing traps

1. **Parallelize-before-cache (WAVE-10 vs. WAVE-09B) is the single most important ordering constraint in this document.** `verify_cited_urls` is called twice on overlapping URL sets (`grounding.py:166`, `synthesizer.py:205`). If WAVE-10 lands before WAVE-09B, the serial duplicate-fetch problem becomes a *simultaneous* thundering herd against the same hosts — more 429s, more risk of IP-level blocking, strictly worse than today. Do not reorder these two waves under any circumstance.
2. **WAVE-06's guard tests will fail against existing data if enabled before backfilling.** The wave's implementation sequence explicitly orders backfill before guard-enablement; an agent that reverses this will see CI go red and may (wrongly) conclude the wave itself is broken rather than incomplete.
3. **WAVE-05's router-singleton fix is likely to break `tests/test_router_fallback.py`**, because the bug (ignoring `config_path`/`quota_tracker` after first call) may be implicitly relied upon by tests that construct a second router expecting isolation from the first. Name this file explicitly in that wave's acceptance criteria so it isn't missed.
4. **Enum name collision risk**: WAVE-05's `CallOutcome` and WAVE-11's `SourceResultStatus` share member names (RATE_LIMITED, QUOTA_EXHAUSTED, TIMEOUT, ERROR) by coincidence of both modeling "things that can go wrong with a network-ish operation." Binding decision 5 reserves both names as separate types up front specifically to prevent an agent working on either wave from "simplifying" by merging them — they model different domains (LLM call outcomes vs. search source outcomes) and a merge would create false coupling.
5. **Four files are edited by two or more waves.** `core/router.py` (WAVE-05, WAVE-07), `core/quotas.py` (WAVE-06, WAVE-07), `cli_app/tools.py` (WAVE-04, WAVE-13, WAVE-14), `agents/deep_research/source_fetch.py` (WAVE-09B, WAVE-10, WAVE-11, WAVE-12). Each wave's `Scope → explicitly out of scope` section names the sibling wave that owns each excluded change — this is the primary conflict-avoidance mechanism, and it's why Track B (`source_fetch.py`) is strictly linear internally rather than allowing any parallelism.
6. **WAVE-15's dependency on WAVE-07 crosses tracks** (Track C depends on a Track A wave) and is the easiest dependency in this roadmap to overlook, because the two waves' subject matter (orchestration vs. quota accounting) looks unrelated at a glance. Concurrent plan steps making concurrent, non-ledger-safe LLM calls would silently overspend a free-tier daily budget and corrupt `data/quotas.db` under race conditions — this is a correctness bug, not a performance nitpick, if the dependency is skipped.
7. **WAVE-11 may need to split into 11A/11B mid-wave** if the `deep_research.web_search` role's fate is decided as "wire it" rather than "reclaim the RPD." The wave's own text pre-authorizes this split; an executing agent should not treat discovering this mid-session as a plan failure.
8. **WAVE-01 deletes the only well-engineered HTTP client in the repo** (`core/requests_client.py`). Its deliverable requirement to transcribe that module's conventions before deletion exists specifically so WAVE-09A (landing much later) doesn't have to reconstruct good defaults from git archaeology mid-session.

---

## Appendix A — Deferred / explicitly not planned

Per binding decisions 3 and 4, the following were identified as real, verified, portable ideas during exploration but are **not** part of this roadmap. A future roadmap revision may pick these up.

- **Prompt registry** (Trend-AI: `contracts/prompts/*.md` with YAML frontmatter — `prompt_id`, `version`, `output_schema` — loaded by a small `prompt_registry.py`, version stamped onto every generated artifact). Genuinely useful for A/B attribution when quality regresses, but deferred — MultiAgent's prompts currently live inline in each agent module, and migrating them is a larger, separate refactor than anything else in this roadmap.
- **Capability router / circuit breaker** (Trend-AI: `app/core/capabilities.py` — users pick a quality tier `fast|balanced|quality`, not a specific model; an 8-state `CapabilityStatus`; `record_outcome()` after every call driving a per-provider circuit breaker with a documented fallback map). This would meaningfully overlap with WAVE-05's `CallOutcome` taxonomy and WAVE-06's registry, but reworking MultiAgent's user-facing model-selection UX (today: explicit provider/model config) into a tier-based UX is a product decision, not an engineering one, and is out of scope here.
- **`.ps1`/`.bat` native Windows launchers, `%APPDATA%` config migration** — binding decision 3. WAVE-04 documents the gap; nothing in this roadmap closes it.
- **Playwright/Puppeteer** as an alternative to Lightpanda — considered and rejected in favor of Lightpanda per the user's explicit request; not revisited.
- **Reintroducing a task queue** (Celery/Redis or any alternative) — WAVE-01 removes the existing broken one; nothing in this roadmap re-adds distributed task execution. If a future need for real distribution arises (e.g. WAVE-15's concurrency needs outgrow in-process threading), that is a new roadmap item, not an extension of WAVE-01.
- **SSRF-hardened RSS/URL fetching** (Trend-AI: `app/trends/real_sources.py:490-943` — IP-pinning, redirect re-validation per hop, response size caps, no auto-decompression). MultiAgent's `fetch_url()` currently has no SSRF hardening at all; this is a real gap, but wasn't in the four priority categories the user selected (evals, cache/budgets) and is deferred. Worth flagging as a candidate for a future security-focused wave, especially once WAVE-14 potentially exposes fetching to more of the chat tool surface.
- **Idempotency keys for resumable runs** (Trend-AI: `app/conversations/idempotency.py` — key + payload fingerprint, safe replay of a `completed` request, `ConflictError` on a same-key-different-payload collision). Would make `multiagent research "..."` safely resumable and prevent double-spending quota on an interrupted run; genuinely relevant to a free-tier-quota-constrained tool, but not selected as a priority. Candidate for a future wave.
- **Two-layer design tokens** (Trend-AI: `design/tokens.json` → `design/tokens.css` raw/semantic split → theme bridge, with a "no hex literals outside tokens.css" lint rule). Would be a natural fit for System A's (Vibe Coding) landing-page generation, giving generated sites free dark-mode support and mechanical no-hardcoded-color linting as a deterministic quality check. Not selected as a priority; candidate for a future wave focused on Vibe Coding output quality specifically.

---

## Appendix B — Finding → wave traceability matrix

| Finding | Location | Wave |
|---|---|---|
| Celery task queue, broken `REDIS_URL` handling | `tasks/celery_app.py:5-8` | 01 |
| Scrapy project, zero callers | `scrapers/` | 01 |
| Selenium driver, zero callers | `tools/selenium_driver.py` | 01 |
| Best HTTP client in repo, zero callers | `core/requests_client.py` | 01 (deleted), conventions feed 09A |
| Docker infra exists only for Celery/Scrapy | `docker-compose.yml`, `Dockerfile` | 01 |
| Dead HTTP/scraping deps | `requirements.txt:29-39` | 01 |
| Celery fallback with bare except | `agents/deep_research/gpt_researcher_wrapper.py:48-73` | 01 |
| Dead prompt constant + dead locals | `agents/deep_research/web_search.py:47-78,209-250` | 01 |
| No `.github/` directory | (repo root) | 02 |
| Ad-hoc per-test monkeypatching of `invoke_router` | `tests/test_cli_app.py:220-270` | 02 |
| Provider registry seam for a fake provider | `core/clients.py:250-266` | 02 |
| No versioned regression scenario suite | (n/a) | 03 |
| POSIX-only command denylist, Windows security hole | `cli_app/tools.py:93-98,805-812` | 04 |
| Duplicated-literal typo | `cli_app/env_setup.py:55` | 04 |
| Windows venv-path probing gap (vs. the function that already handles it) | `agents/vibe_coding/test_runner.py:217-222` vs. `cli_app/tools.py:302-310` | 04 (documented only) |
| Hardcoded `~/.config` (no `%APPDATA%`) | `core/skills.py:49` | 04 (documented only) |
| CRLF injection on Windows writes | `cli_app/tools.py:490` | 04 (documented only) |
| bash-only launchers, `:` PATH separator | `bin/multiagent`, `bin/install-launcher.sh` | 04 (documented only) |
| Router singleton ignores args after first call | `core/router.py:475-487` | 05 |
| Blocking retry sleep | `core/router.py:358` | 05 (noted, not fixed) |
| No retry-on-validation-failure in structured agent runtime | `core/agent_runtime.py:167-218` | 05 |
| Bespoke retry to migrate/delete | `agents/deep_research/synthesizer.py:156-175` | 05 |
| Triple-duplicated provider list | `core/clients.py:52`, `core/config_editor.py:38-46`, `core/quotas.py:64-73,76` | 06 |
| Silent flat-60 score for unbenchmarked models | `core/model_selector.py:445-448` | 06 |
| Missing cascade entry = dead end | `config/model_router.yaml:171-192`, `core/router.py:396-444` | 06 |
| Only successful calls recorded in quota ledger | `core/router.py:308`, `core/quotas.py` | 07 |
| OpenCode Zen provider addition | (external) `opencode.ai/zen/v1` | 08 |
| Other free-provider candidates (NVIDIA NIM, GitHub Models, Cloudflare Workers AI, Hugging Face, Ollama Cloud) | (external) | 08 |
| No HTTP response cache anywhere | `agents/deep_research/source_fetch.py:1267` | 09A, 09B |
| `verify_cited_urls` called twice on overlapping URLs | `core/search_guards.py:270-308`, `grounding.py:166`, `synthesizer.py:205` | 09B |
| bs4 lint-forbidden — must not be introduced | `agents/vibe_coding/web_quality.py:141-146` | 09B (prohibition) |
| Serial per-facet DDG search loop | `agents/deep_research/source_fetch.py:1697-1706` | 10 |
| Serial result-page fetch loop | `agents/deep_research/source_fetch.py:1716-1730` | 10 |
| Serial citation-verify loop | `core/search_guards.py:300-308` | 10 |
| Existing `ThreadPoolExecutor` pattern to match | `source_fetch.py:942,1372` | 10 |
| Only real search engine is a fragile DDG scrape | `source_fetch.py:1592-1677` | 11 |
| `deep_research.web_search` role configured but never invoked | `config/model_router.yaml:152-154`, `web_search.py` | 11 |
| No JS rendering anywhere; SPA/social fetches return near-empty | `source_fetch.py:883-971,892` | 12 |
| Lightpanda integration | (external) `github.com/lightpanda-io/browser` | 12 |
| Pipelines not exposed as outer CLI commands | `cli.py`, `cli_app/commands.py:410-499` | 13 |
| `webfetch` tool returns raw untranslated bytes | `cli_app/tools.py:767-786` | 13 |
| Read tools told they can batch but can't | `cli_app/tools.py:128-129`, `cli_app/agent_chat.py:336-349` | 13 |
| Leftover "hola mundo" debug intercept | `cli_app/agent_chat.py:169-222,38` | 13 |
| New agent-callable tools | `cli_app/tools.py` | 14 |
| Sequential plan-step execution | `cli_app/orchestrate.py:180-262` | 15 |
| Orchestration tooling research (LangGraph parallel branches vs. thread pool) | (research) | 15 |
| `systems.md` §0/§2/§3/§4.2/§8 global coherence | `systems.md` | 16 (local fixes distributed across 05-15) |
| Trend-AI: versioned scenario fixture + coverage meta-test | `Trend-AI/contracts/fixtures/ai-regression-scenarios.v1.json`, `Trend-AI/starter/backend/tests/test_ai_scenarios.py` | 03 |
| Trend-AI: deterministic fake provider w/ injectable failures | `Trend-AI/starter/backend/tests/e2e/fake_provider.py`, `app/providers/content.py:55-306` | 02 |
| Trend-AI: pytest marker taxonomy, keyless CI | `Trend-AI/starter/backend/pyproject.toml`, `Trend-AI/.github/workflows/ci.yml` | 02 |
| Trend-AI: deterministic checks + repair-once-with-exact-errors | `Trend-AI/starter/backend/app/generation/evaluation.py`, `app/services/generate_social_post.py` | 05 |
| Trend-AI: per-failure-class retry budgets | `Trend-AI/docs/04-ai/orchestration.md` | 05 |
| Trend-AI: quota-body classifier | `Trend-AI/starter/backend/app/providers/content.py:562-577` | 05 |
| Trend-AI: single-flight cache, adapter-version-in-key, negative caching | `Trend-AI/starter/backend/app/trends/cache.py` | 09A |
| Trend-AI: reserve/refund/budget semantics | `Trend-AI/starter/backend/app/trends/quota.py`, `app/images/budget.py` | 07 |
| Trend-AI: source status taxonomy, partial validation | `Trend-AI/starter/backend/app/trends/contracts.py` | 11 |
| Trend-AI: versioned decomposed scoring | `Trend-AI/starter/backend/app/trends/scoring.py` | 11 |
| Trend-AI: prompt registry (deferred) | `Trend-AI/contracts/prompts/`, `app/generation/prompt_registry.py` | Appendix A |
| Trend-AI: capability router / circuit breaker (deferred) | `Trend-AI/starter/backend/app/core/capabilities.py` | Appendix A |
| Trend-AI: SSRF-safe URL fetching (deferred) | `Trend-AI/starter/backend/app/trends/real_sources.py:490-943` | Appendix A |
| Trend-AI: idempotency keys (deferred) | `Trend-AI/starter/backend/app/conversations/idempotency.py` | Appendix A |
| Trend-AI: two-layer design tokens (deferred) | `Trend-AI/design/tokens.json`, `design/tokens.css` | Appendix A |

---

## Appendix C — External source register

- **Trend-AI** — `/home/escoto/Documentos/MultiAgent/Trend-AI/`. A separate, unrelated SaaS project (Spanish-language AI content assistant for small businesses) that happens to live inside this repository. Not part of MultiAgent's product; used exclusively as a source of portable engineering patterns for this roadmap.
- **Lightpanda** — [github.com/lightpanda-io/browser](https://github.com/lightpanda-io/browser). Open-source headless browser written in Zig, CDP-compatible, no graphical rendering. Benchmarked externally at ~11x faster / ~9x less memory than headless Chrome for automation workloads.
- **OpenCode Zen** — [opencode.ai/zen](https://opencode.ai/docs/zen/). OpenAI-compatible free-tier LLM gateway, base URL `https://opencode.ai/zen/v1`, no card required. Free model list and per-model rate limits (unpublished as of research date) verified via direct lookup.
- **Free provider research** — general 2026 free-LLM-API landscape survey (NVIDIA NIM, GitHub Models, Cloudflare Workers AI, Hugging Face Inference, Ollama Cloud) used to populate WAVE-08's candidate list; figures are third-party-reported and should be re-verified empirically during WAVE-08's execution, not trusted as permanently accurate.
