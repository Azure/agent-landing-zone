# Design Records: Quality Policy and Compatibility Evidence

These are **proposed development-governance records**, not application entities
or shared runtime schemas. No customer data, API payload, persistence schema,
or file under the umbrella's root `contracts/` changes.

## RepositoryPolicy

Stored in `.quality/policy.json` in each runtime repository.

| Field | Meaning / invariant |
| --- | --- |
| `schema_version` | Explicit supported record version; unknown versions fail |
| `runtime_roots` | Complete first-party source roots, including flat modules and legacy adapters |
| `modules` | Module inventory records, with unique stable IDs and current paths |
| `contracts` | Named allowed/prohibited relationships and protected public/private surfaces |
| `toolchain` | Exact selected checker/parser versions; must match installed distribution metadata |
| `required_checks` | Fixed expected result set; cannot be replaced by whatever jobs happened to run |
| `dynamic_imports` | Explicit supported import-site inventory and associated behavior tests |
| `review` | Owning maintainer role, rationale and policy-review reference |

Changing roots, excludes, tool pins, contract direction, ownership or required
checks is a policy change. Compare it to the protected base, not to a candidate
file's assertion that it was approved. Owners must resolve to real repository
maintainers before activation; an invented team name is not acceptable.

## ModuleSurface

Part of the module inventory. Fields: `id`, `path`, `import_name`, `area`,
`public_exports`, `private_modules`, `allowed_importers`, `legacy_aliases`,
`typing_status`, `responsibilities`, `source_revision`.

A module has one canonical owner. Compatibility adapters reference it and own
no duplicated mutable state. Explicit exports establish the documented public
boundary; arbitrary imports in old tests do not automatically make every private
symbol public. An uncertain external integration must be resolved with a
maintainer before removing its import.

All runtime modules are classified. A move changes path/import name through an
explicit one-to-one record, preserving stable identity and typing protection.
Splits require reviewed responsibility and diagnostic allocation; they cannot
copy the same debt allowance to both destinations.

### Orchestrator storage refinement

At `61b26e4c829c4c2ca81b46926a248cd317a87961`, orchestrator stores these
complete records in `.quality/module-surfaces.json`, under a versioned `entries`
array. Its `.quality/policy.json` module-name inventory remains the immutable
adoption set. Separating current ownership/path records from adoption prevents
an inventory refresh from silently reclassifying newly added code as legacy.
The companion file belongs to the same protected policy and integrity checks;
it does not grant independent approval or weaken any ModuleSurface field.
Stable IDs still bind typing diagnostics, annotation coverage and handler
ownership across recorded moves. Ingestion and UI retain their embedded
ModuleSurface records in `.quality/policy.json`.

## TypingScope

Stored in `.quality/typing-scope.json`. Fields: `schema_version`, `module_ids`,
`coverage_stage`, `planned_expansion`, `move_map`, `review`.

Lifecycle: inventoried -> blocking -> stricter/expanded. No implicit transition
back to uncovered. All newly introduced runtime modules join blocking scope.
Deleting annotations does not remove a module from scope; covered functions
retain typed interfaces or need an explicit policy review.

The report lists uncovered modules separately. `move_map` is an approved
old-path/new-path mapping, never a glob excluding moved code.

## TypingBaselineEntry

Stored in `.quality/typing-baseline.json`; an empty entries list is valid.

| Field | Meaning |
| --- | --- |
| `id`, `module_id` | Unique debt identity and covered owner |
| `symbol`, `source_fingerprint` | Enclosing qualified symbol and normalized local syntax context |
| `rule`, `message_fingerprint` | Diagnostic code and stable normalized message; normalize paths, not semantic types |
| `occurrences` | Exact tolerated multiplicity at that source site |
| `introduced_at` | Original protected source revision |
| `rationale`, `review` | Why inherited debt remains and the approving review reference |
| `removal_stage` | Planned coverage/cleanup stage |

Comparison is a multiset difference of individual diagnostics; aggregate counts
are only reporting. A missing current finding retires its baseline entry in the
same PR, preventing later reuse. Ambiguous fingerprints or unmatched moves fail
for review. A diagnostic in new code never consumes unrelated old allowance.
No baseline is generated or extended automatically by normal CI.

## ExceptionJustification

Stored in `.quality/exceptions.json`. Fields: `id`, `module_id`, `symbol`,
`handler_fingerprint`, `caught_types`, `boundary`, `reason`, `failure_outcome`,
`diagnostic_path`, `evidence_tests`, `review`, `review_by_stage`, `state`,
`expires_on`.

Lifecycle under revised Q5 (ADR-0020): proposed -> active -> retired.
`maintainer-approved` remains accepted legacy metadata, not a prerequisite and
not a consumable state. `active` means eligible for technical validation, not
independent approval. `review` is nonempty provenance, not approval authority.
Candidate registry updates are validated by protected technical rules; changing
the registry alone is not a blocking policy change. Only active,
exact-source-matching records with passing bound evidence are consumed. Changed
catch breadth or failure outcome invalidates the prior fingerprint. No wildcard
handler allowance. Expired,
stale and unused records fail rather than silently extending an exemption.

`failure_outcome` distinguishes propagation, explicit failure translation,
cleanup followed by propagation, and a specifically contractual best-effort
side effect. The latter cannot waive failure for the primary operation.
Evidence tests must execute and pass in the same candidate run.

## CheckRun

A CI artifact, not a versioned product record. Fields: `schema_version`,
`repository`, `base_sha`, `head_sha`, `policy_sha`, `toolchain`,
`check_name`, `status`, `duration_seconds`, `findings`, `coverage`,
`exception_ids_used`, `artifact_integrity`.

`status` is one of `passed`, `violations`, `error`, `not_run`. A finding carries
rule, relative file, location, reason and dependency path where relevant.
Reports omit source payloads, tokens, claims, document contents and environment
identifiers. Job status is authoritative alongside the artifact; a forged
`passed` field cannot compensate for failed/missing execution.

## DeliveryEvidence

PR-linked record: `step_id`, `owner_repository`, `candidate_shas`,
`previous_compatible_shas`, `contract_revision`, `scenarios`,
`command_results`, `documentation_impact`, `recovery_procedure`,
`recovery_result`, `review`.

Each scenario names its frozen pre-change behavior and before/after evidence.
No dependent PR may be needed merely to deploy or recover the current step.
Final evidence binds all three exact candidate SHAs; future tags/manifest pins
must identify that same combination. Approval references are auditable evidence,
not credentials or a substitute for GitHub review enforcement.
