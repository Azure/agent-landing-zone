# Proposed Contract: Repository Quality Gates

**Version**: design 1

**Consumers**: contributors, component CI and repository maintainers

**Scope**: orchestrator, ingestion and UI; FR-001 through FR-008, FR-014/015.

This is the developer-interface acceptance contract. Component draft checkpoints
now provide implementations; their existence does not establish complete
acceptance or shipped enforcement. See the [delivery record](../tasks.md#delivery-record)
for exact revisions and unresolved work. The contract neither changes runtime
APIs nor establishes a shared CI product.

## Q1. Command and result interface

Each component must supply `.github/scripts/check-quality.py`, with this
non-mutating interface:

```text
<repository-python-launcher> .github/scripts/check-quality.py --check all --base-ref <commit> --report <file>
```

The launcher includes the component's protected interpreter-startup requirements.
At the resumed backend milestones, orchestrator requires `python -I -S` and
ingestion requires `python -I`; see [checkpoint commands](../quickstart.md#backend-checkpoint-reproduction).
This refines interpreter initialization, not the shared argument/result contract.
Do not remove required flags to make an older invocation run, or confuse static
source isolation with a sandbox for candidate behavioral tests.

Accepted `--check` values: `all`, `lint`, `typing`, `architecture`, `exceptions`,
`policy`. The default repository is the current checkout; base-ref must resolve
to the fetched protected base commit. Missing base/config/roots/tools, parser
failure, unknown arguments or stale report inputs produce `error`, not success.
No source importing, Azure connection, or baseline-writing side effects.

Exit codes: `0` = every requested check passed; `1` = policy/source violations;
`2` = invalid configuration or incomplete/failed tool execution. Reports conform
to [CheckRun](../data-model.md#checkrun). A new report is bound to repository,
base/head/policy SHAs and installed tool versions. Tools run with explicit config,
no auto-fix, bounded timeout, and fresh or correctly isolated caches.

Test results remain a separate required check using the existing runner. The
quality report must identify whether a violation is lint, type, dependency,
exception-policy, or policy-integrity related; it must not label them all "test
failed". Existing frontend/contract jobs continue to run unchanged.

## Q2. Lint and type policy

Run Ruff across all runtime roots, including legacy adapters, with `E722`,
`BLE001`, `PGH003`, `PGH004`, `RUF100` and agreed correctness rules. Record the
exact selection in `pyproject.toml`; no surprise broad style/format campaign.
Initial violations are repaired or receive individually reviewed exceptions
where meaningful. Do not baseline cycles or create a blanket lint waiver.

Use one checker, mypy, targeting Python 3.12 and the explicit initial modules
in [plan.md](../plan.md). Set `check_untyped_defs`, `disallow_incomplete_defs`,
`warn_unused_ignores` and `warn_unused_configs`; run without incremental caching
when validating unused config. Preserve annotations/typed signatures in covered
modules and grow `disallow_untyped_defs` coverage as modules become fully typed.

Interpret mypy's structured diagnostics using the pinned version. Compare
against individual reviewed baseline entries, never only totals. Full import
following is the default; third-party stub/override exceptions are narrow and
reviewed. Missing third-party types do not justify globally hiding imports.
Unused ignores and unsupported/silent suppression directives fail.

Effective rules include inline mypy directives, Ruff `noqa`/per-file ignores,
discovery roots and nested configurations. An explicit top-level config alone
does not prove absence of weaker inline policy. New suppression directives,
baseline growth or scope reduction require the protected policy-change route.

## Q3. Dependency graph and ownership

Scan static import statements throughout all runtime syntax, including aliases,
relative imports, local imports and `TYPE_CHECKING`. Resolve `from package
import sibling` to that sibling when it is a module; otherwise resolve the
symbol through the exporting module. Do not create spurious facade back edges
from implicit parent-package initialization. Preserve real facade imports and
follow their actual re-export edges.

Use Grimp where it represents importable package roots. Supplement its graph
with standard-library AST resolution for flat first-party files and bridge
imports; cross-check overlapping results with fixtures. Feed the complete
resolved graph to a standard graph algorithm, not just `acyclic_siblings`.
All cycles, including paths through another root, fail with an edge path.
Unresolvable first-party targets and collection omissions are errors.

Known literal dynamic imports join the inventory/graph where resolvable.
Variable dynamic imports require a scoped inventory entry with their permitted
target set and behavior tests. This is not a claim to analyze arbitrary Python
metaprogramming; adding an unclassified dynamic loading site fails review.

Initial rules are grounded in existing responsibility maps, not a newly
invented total layer ordering:

| Component | Concrete contract at gate activation |
| --- | --- |
| Orchestrator | connectors/plugins/telemetry must not depend on API/application entrypoints; existing typed connector/plugin contracts remain public; package consumers may not import declared private modules/members outside their allowed scope |
| Ingestion | jobs/chunking/tools/telemetry/utils must not import API/application entrypoints; APIs obtain scheduler state through the jobs runtime interface, not main's private globals; preserve documented tools/telemetry/config interactions |
| UI | canonical package must not import legacy adapters; lower areas cannot import API/bootstrap; enforce the area graph in the UI contract; legacy adapters may forward only to their declared canonical exports |

Before activation, enumerate actual public exports and private module/member
ownership in policy and the owning `AGENTS.md`. Cross-area ambiguity requires
maintainer agreement. A module beginning with `_` is private by default, but
existing named public modules are not forcibly renamed. Check explicit private
members too; do not make all leading-underscore exports legal because their
containing module is public.

Import Linter `protected` checks direct access to implementations. Approved
facade-to-private edges remain legal while other consumers must use the facade.
Use `forbidden` for genuinely transitively prohibited directions. Select exact
module/descendant semantics explicitly: permitting a package root must not
inadvertently permit every child. Enumerate private modules; do not use an
unsupported partial wildcard such as `package._*`.

## Q4. Broad handlers and public failures

Ruff is only the first check. The complementary AST inventory recognizes bare
handlers, `Exception`, `BaseException`, builtins/import aliases, tuples including
those types and Python 3.12 exception-group handlers. Unsupported indirect
exception-type expressions are flagged for review, not certified safe by
guessing. It is a syntax policy, not arbitrary runtime type inference.

Each broad handler, even one logging/re-raising and therefore exempt from
BLE001, requires an exact technically validated [ExceptionJustification](../data-model.md#exceptionjustification).
No automatic exemption for logs, cleanup, decorator functions, or SDK boundaries.

Required component-specific failure scenarios:

| Component | Existing boundary evidence to preserve and extend |
| --- | --- |
| Orchestrator | Search/Foundry IQ source failure, MCP/OBO failure, orchestration-turn error propagation and existing audit-emitter behavior |
| Ingestion | Queue/run-now scheduler error, config/deployment gate error, retrieval/index/delete failure, strict panel/operator auth and existing best-effort audit emission |
| UI | Backend HTTP failure, malformed/expired/wrong-owner credentials, denied conversation/download access, panel/store error, active-invalid configuration, disconnected-not-ready startup |

Expected output comes from the current public contract, including established
HTTP error/status mappings and safe telemetry. Failure of an optional audit or
owner-index notification may be best-effort only where that existing side-effect
contract permits it; it must not change primary operation success/failure.
Tests assert outcomes and safe diagnostics, not whether a particular `except`
spelling appears in implementation.

## Q5. CI trust, required execution and technical exception validation

Use `pull_request` with read-only permissions and no deployment credentials or
secrets. Never run PR code with privileged `pull_request_target`. Pin actions
to full commit SHAs. Preserve required jobs on PRs to `develop` and `main`
and on merge-queue events if that repository uses a merge queue.

Extend the current component workflow: `.github/workflows/pr_pipeline.yaml`
in orchestrator and `.github/workflows/tests.yml` in ingestion/UI. Place quality
jobs and the aggregate alongside the existing test job, so `needs` observes
real results within one workflow. Do not use unsupported cross-workflow `needs`
or rely on a separate uploader workflow to infer test completion.

The required aggregate check has stable name `quality-gate` and always evaluates
the fixed expected jobs: lint, typing, architecture, exceptions, policy and
existing behavioral tests. A missing, cancelled, timed-out, skipped or neutral
dependency is not passed. An artifact alone is not authoritative; check both
actual job result and matching fresh artifact. Report uploader success is not
quality success.

Bootstrap separately: incorporate policy/checker files through the protected-policy
adoption path, run a clean reference
PR, then have a repository administrator configure rules requiring `quality-gate`
and the existing tests before accepting enforcement as delivered. Do not infer
required checks from a branch's `protected` boolean.

Use the protected-base checker and policy as the minimum policy for ordinary PR
code. It discovers new files independently and automatically covers new modules.
It may accept mechanically proven monotonic scope additions, debt retirement
and unambiguous one-to-one move mappings; candidate settings cannot weaken the
base. Compare policy-relevant pyproject fields, not unrelated packaging metadata.
Exception registry changes are not automatically blocking policy changes.
The protected evaluator technically validates candidate records: exact handler
and caught-type fingerprints, documented boundary/outcome/diagnostics,
unexpired expiry and stage, and passing exact-source bound behavior evidence.
`active` means eligible for technical validation, not independent approval;
`review` is provenance, never approval authority. Proposed or retired records,
unresolved catches, stale sites and missing/failed/skipped evidence cannot
authorize handlers. Only the exact validated site may exempt BLE001.

Other candidate policy modifications remain separately reported and tested.
Checker scripts, evidence runner, aggregator, workflows, tool pins/settings,
typing baseline, policy and CODEOWNERS retain protected-base integrity.
Candidate code cannot lower that minimum by emitting a passing result.
No mandatory independent/latest-head human review is imposed by Q5.
Existing repository review settings are separate and are not changed here.
Authorized protected-policy adoption is still necessary for checker changes;
the old protected evaluator will block this migration until incorporation.
Do not disable CI, fabricate approval or use privileged PR execution.
Diagnostics describe protected-policy differences, not a request for reviewers
or an administrative statement. `CODEOWNERS` is ownership routing, not a Q5
independent-approval requirement.
See ADR-0020 for adoption, fitness functions and rollback.

Policy activation records must show repository rules/settings and execution
evidence. A JSON approval string is evidence metadata, not authority.
If those repository controls cannot be configured, report enforcement blocked.

## Q6. Minimum acceptance fixtures

Run these through the existing component test runner, then use controlled PRs
to prove real merge eligibility once required checks are configured.

| Case | Required outcome |
| --- | --- |
| Clean change, unchanged recorded type debt | Pass; debt reported separately |
| New Ruff violation; new in-scope type diagnostic | Fail with rule and location |
| Remove error A, introduce error B with same total | Fail |
| Duplicate an old error or reuse retired baseline | Fail |
| Delete annotations; drop file from scope; widen ignore | Policy failure, not silent reduction |
| Reviewed move of unchanged module | Same identity/coverage; no new debt allowance |
| Ambiguous move or split copying one allowance twice | Fail for explicit allocation/review |
| Two-node, three-node, cross-root, late/type-only cycle | Fail with complete dependency path |
| Actual sibling import via `from . import sibling` | Resolve correctly without artificial facade cycle |
| Forbidden direct and transitive direction | Fail |
| Private module/member import via absolute/relative/alias syntax | Fail |
| Public facade forwarding to approved private module | Pass |
| Uninventoried variable dynamic import | Fail policy review |
| Bare, aliased, tuple or exception-group broad handler | Fail absent exact justification |
| Logged or re-raised broad handler without record | Fail despite BLE001 exemption |
| Candidate active narrow boundary with its passing bound failure test | Pass only for matching source site; no independent approval needed |
| Stale/unused/overbroad justification; missing behavior test | Fail |
| Checker crash/config parse error/tool timeout | Error; never pass |
| Missing/skipped/neutral test job; stale or wrong-SHA artifact | Aggregate fails |
| Registry-only update with exact unexpired records and passing bound evidence | Pass technical validation; no automatic policy-change finding |
| PR edits baseline/checker/CODEOWNERS to bless its own regression | Ordinary route remains blocked pending authorized protected-policy adoption |

Mutation fixtures use disposable temporary source trees, not persistent changes
to runtime files. No new test framework is required.
