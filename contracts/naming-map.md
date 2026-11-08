# Contract: naming map

**Feature**: 002-agent-landing-zone-rebrand | **Requirements**: FR-001–FR-008,
SC-001, SC-008 | **Research**: R1, R2, R14, R17

This is the single source of truth for every rename. Any other document that
lists old and new names links here instead of copying the table.

## Product and repositories

| Old | New | Version at rename |
|---|---|---|
| GPT-RAG (`Azure/GPT-RAG`) | Agent Landing Zone (`Azure/agent-landing-zone`) | v4.0.0 |
| `Azure/gpt-rag-ui` | `Azure/agent-app-ui` | v3.0.0 |
| `Azure/gpt-rag-orchestrator` | `Azure/agent-app-orchestrator` | v5.0.0 |
| `Azure/gpt-rag-ingestion` | `Azure/agent-app-ingestion` | v3.0.0 |

Repositories are renamed in place so GitHub redirects old URLs (R1). `aka.ms`
short links are retargeted rather than replaced (R2).

## Runtime identifiers

| Old | New |
|---|---|
| App Configuration label `gpt-rag` | `agent-lz` |
| `GPT_RAG_REPO_ROOT` | `AGENTLZ_REPO_ROOT` |
| Other `GPT_RAG_*` environment values | `AGENTLZ_*` |
| Temporary file and folder prefixes `gpt-rag-` / `gptrag` | `agentlz-` |
| `azure.yaml` project name `azure-gpt-rag` | `agent-landing-zone` |
| Telemetry event prefix | `agentlz.` |
| Audit event names `gptrag.audit.*` (`audit-event-v1`) | `agentlz.audit.*` (`audit-event-v2`, `schema_version` 2) |
| Audit `service_name` values `gpt-rag-orchestrator` / `gpt-rag-ingestion` | `agent-app-orchestrator` / `agent-app-ingestion` |
| Repo-root detection by folder name | Detection by the presence of `manifest.json` plus `azure.yaml` |

**Rule:** never use the abbreviation `alz`; it collides with the Azure Landing
Zones brand. Use `agent-lz` (labels) or `agentlz` / `AGENTLZ_` (identifiers).

## Change order (R14)

1. Each component release dual-reads both labels (`agent-lz`, then `gpt-rag`)
   and both environment prefixes (`AGENTLZ_`, then `GPT_RAG_`) for one release.
2. The umbrella switches to writing only `agent-lz` / `AGENTLZ_`.
3. `manifest.json` moves its pins to the renamed component releases.
4. Completed in v4.2.0: components dropped the legacy `gpt-rag` label read
   (orchestrator v5.2.0, UI v3.2.0, ingestion v3.1.1) and read only `agent-lz`.

**Rollback** runs in reverse: restore the previous manifest pins, then the
previous umbrella writer, then the previous component releases. Since step 4,
components read only `agent-lz`, so rolling the umbrella back to a `gpt-rag`
writer also requires restoring component releases older than step 4.

## Naming scan (R17)

`tests/test_naming_inventory.py` searches for the tokens `gpt-rag`, `GPT-RAG`,
`gptrag`, and `GPT_RAG` (case-insensitive). It has no modes or switches: it
fails on any match outside the allow-list below.

**Allow-list** (matches are permitted only here):

- `CHANGELOG.md` entries for releases before v4.0.0.
- Architecture decision records under `docs/adr/`.
- The transition statement ("Agent Landing Zone, formerly GPT-RAG").
- This naming map.

**Temporary entries** (permitted in `v4.0.0-preview.1`; the Phase 2 work
removes them, so the same test enforces the full rename for `v4.0.0`):

- App Configuration label `gpt-rag`.
- `GPT_RAG_*` environment values, including `GPT_RAG_REPO_ROOT`.
- Temporary file and folder prefixes `gpt-rag-` / `gptrag`.
- `azure.yaml` project name `azure-gpt-rag`.
- Telemetry event prefix.
- Folder-name repo-root detection.

| Release | Allow-list in effect | Gate |
|---|---|---|
| `v4.0.0-preview.1` | Permanent + temporary entries | SC-008 |
| `v4.0.0` | Permanent entries only | SC-001 |

### Machine-readable allow-list

`tests/test_naming_inventory.py` parses the two fenced blocks below. Each line
is a repository-relative path glob (`*` stays within one folder, `**` crosses
folders). The scan covers git-tracked files for `gpt-rag`, `GPT-RAG`,
`GPT_RAG_`, `gptrag` (case-insensitive), and the whole word `alz`. New runtime
identifiers use `agent-lz-*` (Search indexes, labels) and `agent-app-*`
(container images), which the scan never flags.

Permanent entries (historical records, specifications, versioned contracts,
legacy-compatibility tests, this map, the scanner):

```naming-allow-permanent
CHANGELOG.md
README.md
docs/adr/**
docs/release-notes/**
**/RELEASE_NOTES*.md
specs/**
.artifacts/**
.specify/memory/constitution.md
.github/copilot-instructions.md
.github/skills/multi-repo-release/SKILL.md
contracts/naming-map.md
contracts/*.json
contracts/README.md
tests/fixtures/historical-runtime-rollback.json
config/governance/tests/test_setup.py
config/panel/tests/test_operator_contract.py
config/panel/tests/test_settings.py
tests/test_naming_inventory.py
config/continuity/setup.py
config/continuity/tests/test_setup.py
tests/test_deployment_modes.py
tests/test_release_contracts.py
```

Temporary entries. `infra/**` covers the AI Landing Zone source incorporated
in-repository with its upstream names (ADR-0015). `config/continuity/setup.py`
is permanent because it recognizes the legacy custom role name and renames it
in place. `Azure/gpt-rag-mcp` is a legacy repository, not renamed and no longer
listed in the issue templates.

```naming-allow-temporary
infra/**
```

### Exact-line inherited package compatibility

The native source gate, customer adapter and cross-component tests must address
the UI's actual inherited Python package, including its packaged schema assets.
This is not a new product identifier or permission to introduce legacy names
elsewhere. The scanner accepts only the complete source lines below in their
exact repository-relative files (ignoring indentation); adding
another token or moving the line to another file still fails.

```naming-allow-exact-lines
config/deployment/native_deploy.py | entrypoint = path / "src/gpt_rag_ui/config/native.py"
tests/test_native_component_binding.py | ui = importlib.import_module("gpt_rag_ui.clients.native_durable")
contracts/examples/inline-presentation/text_only_adapter.py | from gpt_rag_ui.services.native_presentation import text_projection
tests/test_presentation_packaging.py | for variable, package in (("INLINE_ORCH_WHEEL", "native"), ("INLINE_UI_WHEEL", "gpt_rag_ui")):
tests/test_presentation_packaging.py | import gpt_rag_ui.services.native_presentation as implementation
tests/test_presentation_packaging.py | assert pathlib.Path(implementation.SCHEMA) == package_root / 'gpt_rag_ui/contracts/turn-presentation-v1.schema.json'
```
