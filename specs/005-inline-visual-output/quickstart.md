# Quickstart: Validation of Native Inline Visual Output

## Published review handoff

| Repository | Pull request | Target |
| --- | --- | --- |
| ALZ | https://github.com/Azure/agent-landing-zone/pull/876 | develop |
| ORCH | https://github.com/Azure/agent-app-orchestrator/pull/444 | develop |
| UI | https://github.com/Azure/agent-app-ui/pull/191 | develop |
| DOCS | https://github.com/Azure/AI-Landing-Zones/pull/178 | main |

All four PR heads match the published local commits. Both existing screenshots
are tracked in the documentation branch and referenced in all four PR bodies.
Generated Chainlit configuration is preserved in session artifacts rather than
included in the umbrella PR. Internal documentation drafts remain untracked.
No issue comment, release, tag, deployment or manifest pin was published.

The umbrella source and canonical contracts were committed at
`5e18715f21aef156d3828b1278073ccf31821bac`; five canonical contract tests passed
after final staging. Draft schema/hash files now explicitly retain LF through
Git attributes. Final publication does not supersede the component quality
findings recorded below.

The maintainer explicitly approved the development-only
`types-jsonschema==4.26.0.20261006` dependency. Both component requirements and
candidate policies use that exact version. The four existing tool pins remain
unchanged. Policy loaders accept the prior four-tool record or that record plus
the known, exactly pinned stub package, and still reject missing tools, unknown
names and version ranges. The orchestrator discovers the installed stub version
in its isolated tool process. No runtime dependency or quality exemption was added.

The orchestrator's two presentation modules now declare their public surfaces,
responsibilities, consumers, blocking typing coverage and committed source
provenance. Its immutable snapshot in-place union is typed as `NoReturn`,
preserving the raising behavior without a new type suppression. Nonmutating
dictionary union delegates to the inherited implementation. The UI protected
base continues to report candidate toolchain/checker/requirements changes for
review. These controls were not bypassed.

### Approved dependency qualification

The follow-up commits are published in the existing component PRs:

| Repository | Published follow-up HEAD |
| --- | --- |
| ORCH | `a2e60129fcb4ccb3c1a41989d2aeeef601c18331` |
| UI | `1bc2ef6be431f30e95aab3d026686bfa62b3fe30` |

Both PR heads were verified against the published local commits. Their updated
descriptions retain the existing screenshots and report the outcomes below.

| Check | Result |
| --- | --- |
| ORCH settings, schema-stub and quality-policy regression selector | 29 passed |
| UI schema and protected-base regression selector | 7 passed |
| Affected ORCH/UI Ruff | Passed |
| ORCH direct settings mypy | Passed |
| ORCH protected typing | Passed, 37 imported diagnostics outside blocking scope on unchanged files |
| ORCH protected policy | Passed |
| UI protected typing | Passed |
| UI protected policy | Three review deltas for the candidate toolchain, checker and development requirements |

The ORCH protected checks use `python -I -S` and `origin/develop`. Its native
environment now also contains the already-declared Container Apps adapters:
`agent-framework-durabletask==1.0.0b261029`, `durabletask==1.12.0` and
`durabletask-azuremanaged==1.12.0`. They were restored after the hosted-only
environment reported missing imports. `pip check` is clean. No dependency
manifest or runtime pin was changed by that environment restoration.

**Status**: Local runtime/UI technical acceptance and integration evidence.
Azure LIVE validation is removed from completion by explicit maintainer
amendment, not postponed. No Azure operation or issue publication is authorized.

## Maintainer scope amendment — 2026-11-08 (current authority)

The user explicitly requested **removal**, not deferral, of real-Azure validation
from the feature plan. T054 dedicated-target approval, T055 actual-host smoke and
T056 LIVE provider lifecycle are retired without executed checkboxes. They are
not future required work. T057 now covers controlled local public SDK/history/
client interfaces and Playwright: 20 distinct restored-history cases, 20
timing-varied runs, both host agent/workflow shapes, four views/themes, exact
limits and authorization/lifecycle negatives. Those counts remain required.

T058 requires 30 measured renders (95% within one second). SC-008 and SC-010
use automated browser and local provider/publication/hook checks under the
maintainer-approved current technical scope. Default-off, live/current authorization,
source fidelity, provider/hook local parity, pins and global release rules remain.

Azure runtime persistence, ACL enforcement, private-network behavior and deployed
provider parity are **unverified residual risks**, not deferred acceptance gates.
Mocks/compilation do not prove deployment. All older receipts and the NOT RUN
actual-Azure matrix below retain their historical truth, but their old
target/live-gate language is superseded here and in sections 4 / Evidence and exit.
Do not interpret retired IDs in historical receipts as active dependencies.

Documentation placement is **Agent Application → Chat & channels → Inline
visuals**, with one Agents crosslink to per-agent enablement. The user subsequently
approved upcoming What's new and relevant overview/configuration discoverability,
and reuse of the existing actual Chainlit 2.12 captures in docs/PR descriptions.
Candidate source: `DOCS/docs/agent-landing-zone/inline-visuals.md`, nav in
`DOCS/mkdocs.yml`; no publication or shipped-availability claim. Separate issue
screenshot/issue-comment publication approval remains outstanding.

## Final integrated local delivery seal — 2026-11-08

T057-T061 technical deliverables are complete. This receipt supersedes earlier
worktree seals, package versions and qualification results below. Customer docs
describe behavior; the technical outcomes here include successful checks and
material repository quality findings, without claiming all gates passed.

### Exact tested combination and integration

| Repository | Final HEAD | Integrated target (ancestor of HEAD) |
| --- | --- | --- |
| ALZ | `0d755e8da296a9e88e1397cc81bdb43428e28367` plus scoped dirty files | unchanged umbrella base |
| ORCH | `a6c0ae603bc13b7a822f9fc39768c23b9e18d9c6` | `origin/develop`: `ccab58594d0a0b66682d815c3ccac68c34a42862` |
| UI | `d5f70e731b5f09d1747b9d3c1e8900198ba4de6c` | `origin/develop`: `f3da817572c30d637311779ad2d22800d48e57f2` |
| DOCS | `da985d37d49f98965bed28aad31037ccfdd1544d` | `origin/main`: `0b73560fd5ed47c2a60c3cabacf27a4671d4e99b` |

ORCH/UI branches are `feature/inline-visual-output`; DOCS is
`feature/inline-visual-output-docs`. Component feature commits and non-destructive
target merges include the requested Copilot attribution. ORCH preserves current
request-local Foundry headers, native Toolbox ownership/initialization and
enforcement middleware alongside presentation capture/composition. UI retains
upstream optional-delegation/auth semantics. Component tracked worktrees are clean;
DOCS untracked `drafts/` and generated `.artifacts` are excluded. ALZ is uncommitted
for the parent handoff. No push/PR/issue/release or manifest change was performed.

### Commands and current results

Use the existing path inventory below: `$ORCH`, `$UI`, `$DOCS` are component
worktrees; `$V` is `$env:TEMP/inline-declared-qualification-20261108/Scripts/python.exe`.
`$NATIVE` is the existing session-local hosted native environment documented below.
These commands used no Azure services; browser routing allowed loopback only.

| Command / existing entrypoint | Actual result |
| --- | --- |
| ORCH `$NATIVE -m pytest -q tests/test_native_toolbox.py tests/test_native_runtime.py tests/test_native_tools.py tests/test_native_hosted.py tests/test_native_presentation.py tests/test_native_presentation_config.py tests/test_native_presentation_history.py tests/test_native_presentation_multi_agent.py tests/test_native_presentation_safety.py` | **194 passed, 1 skipped**, 120.16s; 14 SDK warnings and a post-suite console-exporter closed-stream diagnostic, not failed assertions |
| ORCH direct Ruff over affected presentation/native files | **Passed** |
| ORCH direct mypy over four affected files, with declared schema stubs and hosted target | **37 imported errors in 8 files**; no feature-file diagnostics. All eight imported files match integrated `origin/develop` after LF normalization: `connectors/{foundry_iq_mcp,aifoundry,cosmosdb,foundry_iq,search}.py`, `telemetry/telemetry.py`, `dependencies.py`, `util/retrieval_backend.py` |
| ORCH protected `check-quality.py --check all --base-ref origin/develop` | **Blocked**, exit 2: development requirements and protected policy pins disagree; policy pins were not changed to force a pass |
| UI `$V -m unittest -q test_native_presentation_history`, `PYTHONPATH="$UI/src;$UI/tests"` | **24 passed**, 2.453s on final HEAD; all H01-H20 below individually passed |
| UI `run-unittest.py --base-ref origin/develop --pattern 'test_inline_presentation*.py' --report .artifacts/final-delivery-unittest.json` | **19 passed**, 19.034s on final HEAD, actual installed Chainlit 2.12, four views/themes, no captures |
| UI `check-quality.py --check all --base-ref origin/develop --test-evidence .artifacts/final-delivery-unittest.json --report .artifacts/final-delivery-quality.json` | **Failed**, exit 1, 162.235s: typing and architecture passed; **25 BLE001 lint**, **30 exception-review**, **1 policy** finding. All 25 lint locations are unchanged target lines. Exception findings concern existing inactive/changed/stale/unevidenced handler exemptions with this focused evidence. Policy finding is specifically `Protected file differs: requirements-quality.txt` (schema-stub dependency), not waived or described as unrelated |
| ALZ existing `python -m pytest -q tests/test_text_only_adapter.py tests/test_presentation_contracts.py`, `PYTHONPATH="$UI/src"` | **10 passed**, 1.36s |
| ALZ `$V -m unittest discover -s tests -p test_presentation_packaging.py -v`, exact wheel environment variables below | **1 passed**, 1.999s; both exact schema/hash assets and extracted package-only readers |
| `python -m pip --python $V check` | **No broken requirements found** |
| DOCS `python -m mkdocs build --strict` | **Passed**, 187.06s; only existing non-nav informational entries |
| Existing `application_guides.check_application_guides(..., only_guides=('inline-visuals','inline-visuals-contract'))` | **Passed**: approved nav, both instructional guides, source/link contracts, accessible self-contained SVG and desktop/390/320 layouts |
| Existing `diagram_controls.check_diagram_controls`, `DIAGRAM_PAGES=('inline-visuals',)` | **Passed**: three viewports, keyboard/focus, zoom/pan, errors, no-JS fallback and Home/Gateway isolation; no screenshots |

The broader integrated UI native/browser/auth/download/reader selection previously
ran 132 tests with one stale expected workflow-text assertion. The canonical reader
now preserves admitted workflow markdown without duplicates; the corrected final
history suite and protected visual suite passed above. Unchanged native/auth/
download cases retain that integrated-source evidence; no pre-merge native results
are promoted as proof of the Toolbox/delegation boundary. Live anonymous auth
rejection remains enforced even for frozen resume settings.

The first final protected browser run hit its five-second installed-app bootstrap
wait before rendering. Only the harness startup wait was separated into a bounded
30-second cap; production rendering and the one-second acceptance criterion did
not change. The successful final run is the current evidence. Initial contract
attempts incorrectly used unittest in the UI venv (pytest is absent there); the
existing umbrella pytest command supplied the actual 10-test result.

### T057 — individual fresh native history cases

Each case uses a fresh service/client and ordinary public SDK/history interfaces,
unique native/presentation identity, repeated stable owner-admitted reads and
owner/deleted-mapping denial before I/O. No source query, new orchestration or
retrofit of native history is performed. H06/H16 preserve two contributions in
ordinal order with distinct agent/source identities. Future versions retain only
readable text; unknown blocks preserve safe known siblings; interrupted output
does not admit an incomplete visual.

| ID | Host | Application | Saved shape | Outcome |
| --- | --- | --- | --- | --- |
| H01 | Hosted | Conversational | visual | PASS |
| H02 | Hosted | Conversational | legacy | PASS |
| H03 | Hosted | Conversational | future block | PASS |
| H04 | Hosted | Conversational | future version | PASS |
| H05 | Hosted | Conversational | interrupted | PASS |
| H06 | Hosted | Workflow | multi-agent | PASS |
| H07 | Hosted | Workflow | legacy | PASS |
| H08 | Hosted | Workflow | future block | PASS |
| H09 | Hosted | Workflow | future version | PASS |
| H10 | Hosted | Workflow | interrupted | PASS |
| H11 | Durable | Conversational | visual | PASS |
| H12 | Durable | Conversational | legacy | PASS |
| H13 | Durable | Conversational | future block | PASS |
| H14 | Durable | Conversational | future version | PASS |
| H15 | Durable | Conversational | interrupted | PASS |
| H16 | Durable | Workflow | multi-agent | PASS |
| H17 | Durable | Workflow | legacy | PASS |
| H18 | Durable | Workflow | future block | PASS |
| H19 | Durable | Workflow | future version | PASS |
| H20 | Durable | Workflow | interrupted | PASS |

The integrated ORCH multi-agent suite requalifies T053's 20 timing-varied runs:
ordered owner attribution, disabled-agent omission, stable saved payload and
unchanged source-call counts. Exact byte/count/expiry/cancellation/reserved-marker
boundaries are covered by the affected presentation/safety suite. Final UI's four
functional permutations cover standalone light/bar, standalone dark/grouped-bar,
embedded light/line and embedded dark/line: native hover tooltip, exact values,
table sort/filter/copy and ordinary identified row follow-ups, no chart zoom/pan/
drill-down, no visual external request. Controlled owner/history/new-action denial
and unsupported/new text-only reader cases retain current integrated evidence.

### T058 — 30 complete-content measurements

Actual device: Windows 11 build 26200, Python 3.12.9, 12th Gen Intel Core i7-1270P,
16 logical processors, 51,189,243,904 bytes physical RAM; installed Playwright
Chromium 149.0.7827.55, headless, viewport 960×900. No private device identifier.
Command: `INLINE_MEASURE_RENDER=1 INLINE_CAPTURE_SCREENSHOTS=0` with the existing
`$V -m unittest` browser selector (PowerShell environment assignments, not shell
prefix syntax). Native packet retrieval and installed application bootstrap precede
the timer; production JSX compile/render, ordinary answer text, full cards/table/
chart/follow-up DOM/layout and two animation frames are included. Each sample
uses a fresh React root and unmounts it. Screenshots/traces remain disabled.

| Sample | ms | Sample | ms | Sample | ms |
| --- | --- | --- | --- | --- | --- |
| R01 | 692.8 | R11 | 42.9 | R21 | 52.2 |
| R02 | 46.3 | R12 | 51.1 | R22 | 32.6 |
| R03 | 40.0 | R13 | 35.8 | R23 | 44.6 |
| R04 | 46.4 | R14 | 50.2 | R24 | 48.5 |
| R05 | 116.4 | R15 | 168.9 | R25 | 270.1 |
| R06 | 43.8 | R16 | 41.5 | R26 | 41.5 |
| R07 | 48.0 | R17 | 43.7 | R27 | 41.8 |
| R08 | 50.0 | R18 | 35.7 | R28 | 41.7 |
| R09 | 35.7 | R19 | 34.4 | R29 | 46.1 |
| R10 | 201.5 | R20 | 201.9 | R30 | 165.7 |

**30/30 (100%) ≤1,000ms; maximum 692.8ms**, satisfying ≥95%. R01-R08 standalone
light, R09-R16 standalone dark, R17-R23 embedded light, R24-R30 embedded dark.
R05/R10/R15/R20/R25/R30 each contain 10 blocks, 500 rows, eight chart series and
1,000 non-null plotted values, with compact envelope ≤262,144 bytes.
Measurement was taken on final production JSX/reader bytes before the test-only
multi-agent/startup refinement; no production render changes followed.
SC-008 maps to the final functional browser checks above. SC-010 maps to T020/
T021/T025/T026/T027's actual local publisher/config/default/removal/hook evidence:
both providers/hooks, one-agent enable/disable/remove/repeated publication,
neighbor/auth preservation and fresh frozen settings with live authorization.
Those shared source bytes and provider locks/module pins are unchanged.

### Exact packages, contracts and handoff

Secure normal pip resolution restored upstream's declared Azure Cosmos 4.17.1,
Blob Storage 12.31.0 and UI setuptools 84.2.1 in the isolated environment.
Chainlit remains 2.12.0; Core 1.24.0/OpenAI 3.38.0/Durable declarations remain
unchanged. ORCH's isolated wheel backend is still declared setuptools 84.1.0;
its declared `types-jsonschema>=4.23.0,<5` resolved securely to 4.26.0.20261006.
No shared tool replacement, TLS bypass, arbitrary pin upgrade or SDK patch.

`python -m pip wheel --disable-pip-version-check --timeout 60 --retries 0 --no-deps
--wheel-dir "$env:TEMP/inline-integrated-wheels-20261108" $ORCH` rebuilt the final
ORCH wheel after the object-schema regression fix. UI's wheel was built from
final production source at `29edf286e3fb87906fa7d889ae9a09653ea4dc6a`; subsequent
`d5f70e7` changes only tests. `--no-deps` is wheel construction only, not runtime
qualification. The runtime graph was separately restored and checked.

| Actual wheel | SHA-256 |
| --- | --- |
| `gpt_rag_orchestrator-0.1.0-py3-none-any.whl` | `6005a0fe6bbbcec28e79a993ac347c4ec6af5154cbc4719be267524988a17fb2` |
| `gpt_rag_ui-3.6.0-py3-none-any.whl` | `83d3812962a6a0febac96b53a9dcdc6fb023eb5472277be079bca08701f7efdb` |

Set `INLINE_ORCH_WHEEL` / `INLINE_UI_WHEEL` to those actual temp paths for the
packaging command. All three canonical schema/hash pairs match both wheels:
settings `98295024fbe702890f2a69faeb086e6f3e526b73c05257f580914363d0225d82`,
selection `48f340384553170cfbc87a10ecc1d3c318078541a271a91e97f472dc332e0a04`,
turn `cdd7543e522417affac96fd90cc602a4b564ead495ae7b02db53d8e17624f07d`.

Final documentation assets are the self-contained
`DOCS/docs/media/runbooks/inline-visuals.svg` and unchanged approved
`DOCS/docs/media/inline-visuals-chat-{light,dark}.png`. The raster diagram was
removed; use SVG in PR links. Built local previews:
`DOCS/site/agent-landing-zone/inline-visuals/index.html` and
`DOCS/site/agent-landing-zone/inline-visuals-contract/index.html`. All browser/
loopback server helpers were closed; no new chat screenshots or media upload.
Customer page, contract guide, What's new (neutral **Upcoming**), application/
settings discoverability and Agents' single enablement crosslink are committed
in DOCS above, not published.

Before separately authorized release binding, coordinate these native producers,
owner-admitted saved-data readers and exact contracts; retain default-off.
Rollback publishes disabled/removed presentation declarations via the existing
publisher but keeps saved readers, current authorization and retention. No new
storage/CDN/Azure resource or default deployment burden. Manifest SHA-256 remains
`89f591314b4014cd33b12df9a7586ae72c64c35054bd1792e31d6e5740541dae`;
image digests are unavailable because images were not built. Azure runtime
persistence/ACL/private networking/deployed parity remain unverified residual
risks, not implementation gates. Parent owns ALZ commit, pushes and PR preparation;
issue publication and release/pin changes have no authorization.

### Final source/report fingerprints

SHA-256 of actual bytes, captured after component commits and final task closure.
Component HEADs bind all tracked feature files; the explicit fingerprints below
also bind dirty umbrella implementation/acceptance files and local reports.
Quickstart excludes itself. Historical tables below are not current seals.
Final verification: all **54** source/report fingerprints match current bytes;
all four `git diff --check` commands pass. The **58** active tasks are checked,
unique and have no unresolved/retired prerequisite references. Read-only
requirements checklist: 16 checked, zero unchecked. Existing prerequisite command
resolves this feature directory. No execution/browser helper remains running.

| Source / evidence | SHA-256 |
| --- | --- |
| ALZ `CHANGELOG.md` | `1ae99564fe4f1771c792d55f5adb00861e7602f2e9cffd6e18e35f304ce28339` |
| ALZ `config/deployment/app_settings.py` | `9d298c7274895dd1a6469ace7dd093f0284d3e2745b69f41cdde1fb7c3041b53` |
| ALZ `config/deployment/appconfig_intent.py` | `459cceda77870a9cf137076ead190ac458d54a26deb6a1b654c4bca65ef3344b` |
| ALZ `config/deployment/presentation_settings.py` | `4bf2e91ebab608874f017c179bc6b47e91a78c99104553c918f2e7174fc17e6b` |
| ALZ `config/deployment/appconfig_ownership.json` | `20d9077756492230aa24aa9f01fd548fce58c49d20c7d7c998926b574ac869a8` |
| ALZ `contracts/README.md` | `5722730cebec5bb2ef5467dbda4469db629722c86f0d6fbfe1dacfa80fbd4182` |
| ALZ `contracts/examples/inline-presentation/text_only_adapter.py` | `b7dfd68e262b214c804ebb67608855911bc624512706fb5a2d747ed5c8fbbdfa` |
| ALZ `tests/test_app_settings_resolution.py` | `d1f1de51293baac0b950afef7398c1542791a98aa9ed30aeef29beefc4cb6477` |
| ALZ `tests/test_appconfig_intent.py` | `6191b95573bdd0f885fcaa77a4cf1ac185b086752042586614e1ddc577430548` |
| ALZ `tests/test_infra_provider_hooks.py` | `30f81ccc4cfa0c6bcad94061d52722256c55fd71c309217c26fcf3325898f1be` |
| ALZ `tests/test_presentation_settings.py` | `40a1b4ec33ed535a227081402f0a7bf719e1eaaccb7cba1627adeb0774e54d84` |
| ALZ `tests/test_presentation_contracts.py` | `3ac65876b2702426a8deb7b9880db53b721113fd8d415c2b74b1c1c984a195fd` |
| ALZ `tests/test_presentation_packaging.py` | `1ca174b7e0de5a8a75ef4c387ce5be09751b685b53b66f8961473a66279b0f61` |
| ALZ `tests/test_text_only_adapter.py` | `cff2dfee23f80c68d6469ccf49952145261faa8ab2112fc2dff2afaa0788139a` |
| ALZ `specs/005-inline-visual-output/tasks.md` | `4db64982ea6be3f2a04d0242208f5bf2be2af528c3b9f473a7f871b7fe9b7ebe` |
| ALZ `specs/005-inline-visual-output/spec.md` | `05f44b32ecad2bda09a179436f83e5ab6ab6cce1b9bd52b2473c02cd51332569` |
| ALZ `specs/005-inline-visual-output/plan.md` | `ca47a43044dabe8bfd1aae14e084775a42e257ce3591aed0e5e020a05bdcd726` |
| ALZ `specs/005-inline-visual-output/contracts/delivery.md` | `683557f94361ea5e25994e09feaa96a073730bd15aa3df90bbd88ad4dc50905b` |
| ALZ `docs/adr/ADR-0040-native-inline-presentation.md` | `629c354feea24fc747f8730de5f63073a2d956a38fa8e7a287b6527ea687baa2` |
| ORCH `src/native/agent.py` | `df52fb03405123b4d9095d25ee54db68d7966f6bcb34c6d8d81b3485a953c35a` |
| ORCH `src/native/config.py` | `1dd11567e0e15e9dabe978c252882bcfa2ea70a46729f37eb2e4c843160a93d7` |
| ORCH `src/native/presentation.py` | `5b3b55cdc4aed81cc82346c0be9d10dccb1d82a684d108224fee509618451282` |
| ORCH `src/native/presentation_middleware.py` | `4a54125d7dc7fd851934f132d54db81f5aea419879702c78715f1027642dbc8b` |
| ORCH `src/native/workflow.py` | `48992ed9b592f5270badbe1e983b29fde15c03313fdcf767654444dc590156ef` |
| ORCH `tests/test_native_presentation_config.py` | `749daedcd1776a5ba63e56d1e1688f25154e8a69ae8976bca5f84cd3ada3755b` |
| ORCH `tests/test_native_presentation.py` | `96c5e2ecbfe4fb5c64226adfd65aa15681d80f22c8cdefbd7f49f4b9cd81b46c` |
| ORCH `pyproject.toml` | `3320714eb657282764730ebee661cad7d2335b533eb3d8c968f1638951579b6b` |
| ORCH `requirements.txt` | `a5cfccb6c0f4de5587fb7bf0da1e2b57a9d1c19a179e56116bf35f8ef6e53f7b` |
| UI `src/gpt_rag_ui/services/native_presentation.py` | `2d41b3aa2f222e37de55aee099acc5f024ae7c7bc8bf3b276fc9a033d617c146` |
| UI `src/gpt_rag_ui/services/native.py` | `d00d1250bcd75327f620b7db9fdf0545df6d38b3280fae20bb57de158408698f` |
| UI `src/gpt_rag_ui/api/native.py` | `9fcbeb758d65e6721c99f4fb1538e74b72d683e1be6ed7233964e489905e72e6` |
| UI `src/gpt_rag_ui/api/native_chat.py` | `68832e63acbf2fbe4c9ad9459caf4dcb0ee0183bcc31f94673fb4e221cfc533a` |
| UI `public/elements/Presentation.jsx` | `51f631cb147ffd79f3e514219fb9a3a576c43bc4bcb2f44f4ddd56b4915dfc80` |
| UI `public/custom.css` | `1ea5e3b2a45ae5049d09c07458fdf0e47b67dad8173e705a28f2cdef412991f4` |
| UI `tests/test_native_presentation_history.py` | `d1bb436177b69e47e9e64336a8bc5d6bc99cf04b4590c3a47ad78f78007caf7c` |
| UI `tests/test_inline_presentation_browser.py` | `84ccdd53c4f22dd0a6bfbb4c87be29e260a5674c10ee753c388ac59491f22b63` |
| UI `.quality/policy.json` | `7c442f5fe67b5c84e72084c1f7d4bc42a064ae435be55e5282e53c3d82594aa0` |
| UI `.quality/typing-scope.json` | `c4dcdffa36df1a72eb1e26730c0cb31646c99ff7e47d598a56002a159f6619d9` |
| UI `requirements.txt` | `2bcff4aa6d4cb8b191f18137d0f5df547ae870b3752519a3aedeea2f501148a7` |
| UI `requirements-quality.txt` | `2e292e698ecc06ac2f8a5727d8111ee9cd03b453cdf2d8b4682279d03ea8e434` |
| UI `.artifacts/final-delivery-unittest.json` | `e8766fd2ec20a6d8264402939b4d111607c6b26ab28397ba573ffdac9044e7e7` |
| UI `.artifacts/final-delivery-quality.json` | `f87b40155c9743163254a5208c55cf9fa0b8faa583e7cca99e5dce72e629072c` |
| DOCS `mkdocs.yml` | `fc6466d2b25c55c3bc624eb138e2c99041eeeba260cc3b4699a47dddb86c375e` |
| DOCS `docs/agent-landing-zone/inline-visuals.md` | `c9cb7e9b3192d887aca5a625dc8ff8ddb82615057c816ac799894fae73e99c69` |
| DOCS `docs/agent-landing-zone/inline-visuals-contract.md` | `8e63e1a45fc80bd302533bda61f119d2822b2334121f90b098d3fa56484d04ab` |
| DOCS `docs/agent-landing-zone/whats-new.md` | `3c2881c305c799ce5727fb1598349d2e52a4791e49b57c256203d89056b066b9` |
| DOCS `docs/agent-landing-zone/application.md` | `522a848ee0419c42cd0b5a82050613c90317756b381c9d1d83e8ded79ecb38fb` |
| DOCS `docs/agent-landing-zone/application-settings.md` | `e5507aacdbc8354144f08684122412cd6bc2f660bd1fce214cd1741047e818ce` |
| DOCS `docs/agent-landing-zone/agent-strategies.md` | `2697378f416f9ea5d4a49670f0d37d433d1b1c1d579ae0d4076a42cd137367c6` |
| DOCS `docs/media/runbooks/inline-visuals.svg` | `24559998b237792539fd884ab26b776d02b73e16c47cc0f2f068b5ac984eb5a5` |
| DOCS `docs/media/inline-visuals-chat-light.png` | `4d5ecdb537bd97db77e26dfcc9fec22b5654b3f2449c1e70fa6d14bd44b639a3` |
| DOCS `docs/media/inline-visuals-chat-dark.png` | `cd579869814cb0814e747b5b1894d8a05e2eb3ebee9e7d9e54309d5e62c717d4` |
| DOCS `tests/home/application_guides.py` | `275afdee123905105e26de747c67ac3a8e6f1ffa738a1b3190fa0d6d8e090468` |
| DOCS `tests/home/diagram_controls.py` | `c9a61cf02ae450e1c410459c5664cc332ff2beda41ea747eebab42f6b5e6d089` |

## Historical pre-integration local delivery seal — superseded

This earlier worktree receipt retains historical commands, results and hashes.
Its revisions, dependency versions, browser failures and acceptance status are
superseded by the final integrated seal above. T002/T003 inventories remain valid
without new research. The current acceptance definitions are in spec/plan/tasks.

### Delivered documentation and approved media

In the existing DOCS feature worktree:

- `docs/agent-landing-zone/inline-visuals.md`: approved Chat & channels placement,
  Objective / Expected outcome / When to use / Prerequisites / Procedure with
  numbered steps / Validation / Troubleshooting / numbered Rollback. Terminology,
  admonitions and diagram wrapper follow the actual Teams/Microsoft 365 and
  Copilot Studio runbooks, without their irrelevant channel-publication inputs.
- `docs/agent-landing-zone/inline-visuals-contract.md`: central schema/hash,
  typed-source fixture and safe text-only adapter reference, registered under
  Development & customization. Canonical schema/sample files stay in ALZ.
- `agent-strategies.md`: enablement crosslink only. `application.md`,
  `application-settings.md` and `whats-new.md`: narrowly approved discoverability,
  with **Upcoming (unreleased)**, no invented release version or current availability.
  Global `docs/whatisnew.md` was inspected: it owns site-wide milestones and
  already points to the product What's new page, so no duplicate announcement
  or unrelated historical-release edit was added there.
- `docs/media/runbooks/inline-visuals.svg` and `.png`: authored/rendered diagram
  matching incumbent Segoe UI, blue panels, service boxes and arrow styling.
  Native output enters owner admission **before** UI rendering. Disabled agents
  bypass the extra stage. SVG is self-contained; no script/foreign HTML/resource URL.
- Existing UI `chat-light-desktop.png` / `chat-dark-desktop.png` were copied
  byte-for-byte into `docs/media/inline-visuals-chat-light.png` /
  `inline-visuals-chat-dark.png`. These are **synthetic data, actual Chainlit
  2.12.0, local mock agent**, not authenticated Azure deployment proof.
  Captions explain the request, ascending revenue sort and theme change.
  No new chat/page screenshots were captured. Only the new diagram was rendered,
  within two rounds. Captures are outside `runbooks` so the site does not give
  them automatic diagram controls.

Prepared PR-description references (repository source paths, not uploaded media):
`docs/media/inline-visuals-chat-light.png`, `docs/media/inline-visuals-chat-dark.png`
and `docs/media/runbooks/inline-visuals.png`. The approved docs/PR reuse does
**not** authorize issue posting. New files remain unstaged/uncommitted for review;
resolve asset links against the reviewed PR head only after an authorized push.

Local preview artifacts: `DOCS/site/agent-landing-zone/inline-visuals/index.html`,
`DOCS/site/agent-landing-zone/inline-visuals-contract/index.html` and the diagram
PNG above. All self-contained browser/server helpers were closed.

### Actual commands and results

| Command/check | Actual outcome |
| --- | --- |
| Existing umbrella runner with `$env:PYTHONPATH="$UI/src"`: `python -m pytest -q tests/test_text_only_adapter.py tests/test_presentation_contracts.py` | **10 passed, 1.28s**; owner gate, legacy/future text safety and exact contract examples |
| `$V -m unittest discover -s tests -p 'test_presentation_packaging.py'`, with `INLINE_UI_WHEEL` / `INLINE_ORCH_WHEEL` pointing at the actual wheels below | **1 passed, 7.725s**; exact schema/hash bytes and package-only readers for both components |
| `python -m pip --python $V check` | **No broken requirements**; declared isolated UI graph unchanged |
| UI protected `run-unittest.py --base-ref origin/develop --pattern 'test_inline_presentation*.py'` with `QUALITY_RUN_ID` and report path | Reused current-source evidence: **19 passed, 87.921s**, actual reader/handler/browser modules |
| UI protected `check-quality.py --check all --base-ref origin/develop --test-evidence .artifacts/local-delivery-unittest.json` | **Failed**: typing/architecture passed; 25 lint, 30 exception-review and 4 policy findings. Feature-associated native reader inventory/blocking typing classification and removed shape annotations are not dismissed as unrelated baseline |
| ORCH `$V -I -S .github/scripts/check-quality.py --check all --base-ref origin/develop` | **Blocked**, exit 2: development requirements and protected policy pins disagree |
| ORCH direct Ruff over four native feature files and config test | **Passed** |
| ORCH direct mypy over four native feature files using the hosted Python target | **Failed**, 55 errors/10 files: relevant middleware union/finalizer errors, target stubs and imported baseline errors |
| ORCH existing pytest config selector `-k 'presentation or snapshot or turn'` | **8 passed, 11.56s** |
| DOCS `python scripts/planner/validate_catalog.py` | **Passed** |
| DOCS `python -m unittest discover -s tests/planner -p 'test_*.py'` | **19 passed, 0.251s**; printed 503/429 cases are mocked unit tests, no Azure price query |
| DOCS `python -m mkdocs build --strict` after final technical-page fix | **Passed, 57.70s**; only incumbent non-nav informational entries `portal/Readme.md` and `terraform/index.md` |
| `application_guides.check_inline_visuals_source()` | Tests first failed for missing headings and capture/control placement; final run **passed**, including ordered text-reader steps and SVG safety |
| Existing rendered `browser_checks.py --application-guides-only`, loopback-only routing, 15s navigation bound | **Failed/partial**: timed out on existing `user-feedback`, not an Azure request |
| Existing rendered guide helper, smallest `only_guides=('inline-visuals','inline-visuals-contract')`, loopback-only routing, 30s navigation bound | **Failed/partial**: approved nav set and Inline visuals at 1440/390/320 passed before the new technical page lacked ordered instructions. Fixed surgically; no third browser round performed |
| Final built-HTML ordered-list/media/alt checks | **Passed**: each new page has three ordered steps; one eligible diagram, two non-diagram captures with accessible alt text |
| Focused diagram expansion/modal control selector | **Not completed**: prior guide assertion stopped the combined runner before this selector; do not claim a pass |
| Task retirement/dependencies, affected relative links (query/fragment stripped), both changed-repo `git diff --check` | **Passed**: 58 active IDs, T054-T056 retired without executed checkboxes or dependency/traceability references |

The first attempt incorrectly used pytest inside the UI's isolated runtime,
which has no pytest module because UI's declared entrypoint is unittest.
No arbitrary test dependency was installed: the existing umbrella pytest runner
and isolated standard-library wheel check above supplied the actual passes.

### Exact revisions, packages and dirty-source fingerprints

| Worktree | Actual HEAD | Branch |
| --- | --- | --- |
| ALZ | `0d755e8da296a9e88e1397cc81bdb43428e28367` | `feature/inline-visual-output` |
| ORCH | `59f2de72b07f3b8e182e6afabdcf24a056886ef3` | `feature/inline-visual-output` |
| UI | `a1e0979c3389526c4483c43dabec4e660519ad57` | `feature/inline-visual-output` |
| DOCS | `4cf3b3c099bd00021e99e57ff9a750d043eded0e` | `feature/inline-visual-output-docs` |

Actual isolated runtime remains Python **3.12.9**, Chainlit **2.12.0** and
setuptools **84.1.0** with all 27 UI runtime declarations matched; controlling
pip is **26.2.1**. Existing Playwright/Chromium supplied local rendering, not
an arbitrary runtime dependency overlay.

| Actual wheel under `$env:TEMP` | SHA-256 |
| --- | --- |
| `inline-declared-ui-wheel-ap3k0mjm/gpt_rag_ui-3.5.0-py3-none-any.whl` | `f8c5e4e6b09cfe6378ce06074cc8d50b6c993400faa922aeea0cb7c5e8c5f9d7` |
| `inline-declared-orch-wheel-lit234zr/gpt_rag_orchestrator-0.1.0-py3-none-any.whl` | `38a812531005570648d19e3346b2449f2f426ae92aab04ee9d7e400619542575` |

Current-source fingerprints, not a claim these HEADs contain the dirty feature:

| Source / evidence | SHA-256 |
| --- | --- |
| ALZ `config/deployment/appconfig_intent.py` | `459cceda77870a9cf137076ead190ac458d54a26deb6a1b654c4bca65ef3344b` |
| ALZ `config/deployment/presentation_settings.py` | `4bf2e91ebab608874f017c179bc6b47e91a78c99104553c918f2e7174fc17e6b` |
| ALZ `contracts/examples/inline-presentation/text_only_adapter.py` | `b7dfd68e262b214c804ebb67608855911bc624512706fb5a2d747ed5c8fbbdfa` |
| ALZ `contracts/examples/inline-presentation/README.md` | `951d10030b6380dbe8d3b159fe7e53e5f83e0b45bfc84aa4ee7418df4c347199` |
| ALZ `specs/005-inline-visual-output/tasks.md` | `3c4f9702f809f9867d9d4af8e4282f7e8b8ef8b987327a12c861d31b76c2d16e` |
| ALZ `specs/005-inline-visual-output/plan.md` | `c45086f6c1509546305e98a127d83202b4a29e2bdecd16eb44714a50701a1000` |
| ALZ `specs/005-inline-visual-output/spec.md` | `82066900d60bdb810ddfe8644090a154091aa63f7b2f3f738a5787d3cef23fc6` |
| ALZ `docs/adr/ADR-0040-native-inline-presentation.md` | `ff4ed37223c95375cc46f72fee770facd2c8d5f03187c2a9af64f07a06d7b5bb` |
| ALZ feature `contracts/README.md` | `f5b015de2e6589823582458ab07f63aeb71133f422bf4f66239ab4cf3d88306a` |
| ALZ feature `contracts/configuration.md` | `df71cb164e6a0a38ebe7654df74a952d3c001eae1e21d96dd94b4c2d1d74fa77` |
| ALZ feature `contracts/delivery.md` | `187425bb184150807e12bb2db6b86a74bceb3f48e3f07cfcb6b6c52b02ad4a4e` |
| ALZ `contracts/README.md` | `5722730cebec5bb2ef5467dbda4469db629722c86f0d6fbfe1dacfa80fbd4182` |
| ORCH `src/native/agent.py` | `925cc9cc5125a28cdcf829c74a7d517ec053583a98ee00228502899e009cccf0` |
| ORCH `src/native/config.py` | `89b421f8b7b852dbfd877dce36af70d92e259452027c78ceb2c6d4e1106d9d9b` |
| ORCH `src/native/presentation.py` | `88d6ba17922aee739ae63ff46fcf3c142ad0dc132dd272962a2a36032613257a` |
| ORCH `src/native/presentation_middleware.py` | `5d5dcf3d8f4d38ceb357d14b004a02ac94888c88e89d41b4103ee0c0e2a913d5` |
| ORCH `src/native/workflow.py` | `48992ed9b592f5270badbe1e983b29fde15c03313fdcf767654444dc590156ef` |
| UI `src/gpt_rag_ui/services/native_presentation.py` | `c36ea255e7977e634e373cdb4c8ad7cb48ed588c10cd1c4bbaa6786b2a23c03d` |
| UI `src/gpt_rag_ui/api/native.py` | `72591d6d991fac6c30f4bf0f51d7fdd82223dcf3536648b0e5e27ef5675b501a` |
| UI `src/gpt_rag_ui/api/native_chat.py` | `6f7cc7751b5176614b100e5c255080dfb207a92587a1716e0c00085e7f672a17` |
| UI `src/gpt_rag_ui/services/native.py` | `ab074b3ece5017649905d63cbf684082d56538b4712d7bfd8dbf9a7e4fa9499f` |
| UI `public/elements/Presentation.jsx` | `51f631cb147ffd79f3e514219fb9a3a576c43bc4bcb2f44f4ddd56b4915dfc80` |
| UI `public/custom.css` | `1ea5e3b2a45ae5049d09c07458fdf0e47b67dad8173e705a28f2cdef412991f4` |
| UI `.artifacts/actual-chainlit/evidence.json` | `2a57401e8f0025cac6aea85de65b978ea1abef2a470d7a8fc6c348b661bb8857` |
| UI `.artifacts/local-delivery-unittest.json` | `20ece5e3ca678efd9fb5eae3e7018f382e625e7f294c291065af665ef715f27d` |
| UI `.artifacts/local-delivery-quality.json` | `4f4d2fc57f0897ef91b46ba3a0ded556a31b7c3bb2644c729b1898c78052c703` |
| ORCH `.artifacts/local-delivery-quality.json` | `b36f8b0007433bf00e0d22f305080bfbc6a58a2ab0c9291f5ccd138a8eadac2f` |
| DOCS `mkdocs.yml` | `fc6466d2b25c55c3bc624eb138e2c99041eeeba260cc3b4699a47dddb86c375e` |
| DOCS `docs/agent-landing-zone/inline-visuals.md` | `b88968b3ee2a88463c6186628cf49eebfb6c01644e6b4ee31ace505328aded51` |
| DOCS `docs/agent-landing-zone/inline-visuals-contract.md` | `12b8dac9510b3758cc3e07ec6a5eab29f063b4d082e478a0258265d0ae2a30eb` |
| DOCS `docs/agent-landing-zone/whats-new.md` | `e557af94dafee27bb1b01330c5e4da68140f70e087be6477f252338147d2632c` |
| DOCS `docs/agent-landing-zone/application.md` | `69858bce0bbb8b52f24aef5aedb4959cdfe4085b5c47f72a867091e4fffe1e18` |
| DOCS `docs/agent-landing-zone/application-settings.md` | `d53c4006ded5c0b1423185e85b5946af08a4f927de4c9b93f3c1bf21f6a688f0` |
| DOCS `docs/agent-landing-zone/agent-strategies.md` | `1d45602b0594ae8747a1563e475d2c806322ed9c871059a5cb20b039f203fcef` |
| DOCS `docs/media/runbooks/inline-visuals.svg` | `9d98f92bf6f09529e6a3a63d8b95f418b20d30fbe02b7d8b5b6aba9e5bab1d53` |
| DOCS `docs/media/runbooks/inline-visuals.png` | `272848f4dae524c03b37db139ee3a8e570fa3019291f3d01ca61e63d0687f827` |
| DOCS `docs/media/inline-visuals-chat-light.png` | `4d5ecdb537bd97db77e26dfcc9fec22b5654b3f2449c1e70fa6d14bd44b639a3` |
| DOCS `docs/media/inline-visuals-chat-dark.png` | `cd579869814cb0814e747b5b1894d8a05e2eb3ebee9e7d9e54309d5e62c717d4` |
| DOCS `tests/home/application_guides.py` | `74b65d695cd15097bb8b748f09f21762d94d3272b80e8314bcfa14c348b386e0` |
| DOCS `tests/home/diagram_controls.py` | `c9a61cf02ae450e1c410459c5664cc332ff2beda41ea747eebab42f6b5e6d089` |
| DOCS `drafts/agent-landing-zone/inline-visual-output.md` | `a594e545b7efe188b2d923480ba6140edcd379b2c75b38b85a03538d97faaa81` |

The three canonical schema/hash pairs are unchanged and requalified against both
wheels. Feature contract paths above are relative to `specs/005-inline-visual-output/`;
the separately named ALZ root `contracts/README.md` is not that feature README.
Quickstart is excluded from its own fingerprint to avoid a self-referential hash.

### Remaining local acceptance and release/rollback handoff

- **T057:** complete retained 20-history/20-timing-varied/four-view local matrix
  counts, public Hosted/Durable agent/workflow and lifecycle/action-denial coverage.
- **T058:** 30 measured renders and automated browser/provider instruction checks.
- **Quality/docs qualification:** protected ORCH pin agreement, relevant native
  typing/policy findings and complete browser/modal controls are not claimed solved.
- **Azure:** retired NOT RUN evidence is historical; runtime persistence/ACL/private
  networking/deployed parity remain unverified risks, **not future required gates**.
- **Release binding:** manifest remains ALZ v7.2.1, ORCH v7.1.0 /
  `666d39862590cfb165097ee55737a1ef66fd2afc`, UI v3.6.0 /
  `8a45595aa321d8841e7a4555d542b890beebf1b0`. Manifest SHA-256 remains
  `89f591314b4014cd33b12df9a7586ae72c64c35054bd1792e31d6e5740541dae`.
  Actual candidate UI wheel is **3.5.0**, not proof of manifest v3.6.0 binding.
  Images were not built/bound: digests are **unavailable**.
- A separately authorized release must coordinate matched native producers,
  saved-data readers and exact contracts before opt-in; no pin/tag/image is
  invented here. Rollback disables new visual production via the existing
  publisher while retaining owner-admitted saved-history readers, auth and
  retention behavior. No new storage, CDN, default resource or deployment input.

No Azure API/CLI query, login, environment/demo change, dependency upgrade, auth removal,
commit/push/release/PR/issue publication occurred during this documentation delivery.
Existing unrelated UI CSS whitespace remains separate and unchanged.

## Declared runtime/UI qualification — 2026-11-08, completed local continuation

This receipt supersedes earlier **unavailable Chainlit/setuptools**, TLS and
missing durabletask/dotenv claims below. Those failures remain historical
attempts, not current blockers. Full quality/release binding and local technical
acceptance are not promoted by these focused local results.

### Actual isolated dependency graph

Modern pip **26.2.1**, Python **3.12.9**, normal system TLS trust and authorized
`https://packagefeedproxy.microsoft.io/pypi/simple/` securely resolved and
downloaded **Chainlit 2.12.0** and **setuptools 84.1.0**. Both versions exist in
that configured feed. No trusted-host, TLS bypass, arbitrary repository pin
change or shared environment replacement was used.

UI environment: `$env:TEMP/inline-declared-qualification-20261108`;
`pyvenv.cfg` has `include-system-site-packages = false`.
All **27** actual `UI/requirements.txt` declarations match installed versions,
including extras' required cryptography; final
`python -m pip --python $V check` reports **No broken requirements found**.
Declared ranges resolved to jsonschema 4.26.0, FastAPI **0.141.1**, pydantic
2.14.2, PyJWT 2.15.1 and Starlette 1.10.0. All exact pins remain exact, notably
OpenAI 3.38.0, Agent Framework Core 1.24.0, DurableTask framework
1.0.0b261029, durabletask 1.12.0, Azure App Configuration provider 2.5.0,
Azure Monitor 1.8.9/exporter 1.0.0b55 and HTTPX instrumentation 0.64b0.

The earlier 240s full-graph attempt was not retried wholesale. Normal
dependency-resolving installs proceeded in native/durable, web and Azure
client/telemetry groups, with **600s bounded waits**. A session-only
`constraints.txt` copies all actual runtime names/specifiers; the `[crypto]`
extra is retained in requirement arguments but omitted from the constraints
syntax because pip rejects extras in constraints. No source requirement changed.

Two advertised PEP 658 `.metadata` URLs returned HTTP 404, for selected
`opentelemetry-instrumentation-langchain` and `-weaviate` 0.63.0 wheels.
The corresponding advertised wheels themselves downloaded securely and
matched their authorized simple-index SHA-256 values:

- LangChain: `2fb47e5b1b820bd70a6ad90c39fa389766e2ca05140e8b518f280b99b0b41092`
- Weaviate: `8e88a0d34245927a006f0c7f16ce82fc20d23dc84f0b7d0cb9a9863761a94514`

Those unchanged wheels were supplied as local requirements to normal pip
resolution, with all dependencies enabled. This repairs artifact metadata
retrieval only, not a production SDK patch or a fabricated version.
Resolving the overlapping declared Chainlit/FastAPI/Azure Monitor/HTTPX
instrumentation group then backtracked normally to compatible FastAPI
0.141.1 and OpenTelemetry **1.43.0 / 0.64b0**. Two now-unreferenced incremental
orphan packages (`opentelemetry-exporter-otlp-common`,
`opentelemetry-exporter-http-transport` 0.66b2) were removed only from this
new venv after checking reverse requirements. Final pip check is clean.
No `--no-deps` result is used as completed runtime qualification.

Actual command structure (from any directory; `$UI` is the inventory path):

```powershell
$V = Join-Path $env:TEMP 'inline-declared-qualification-20261108/Scripts/python.exe'
$D = Join-Path $env:TEMP 'inline-declared-qualification-20261108'
# $D/constraints.txt is the session-only normalized copy described above.
python -m pip --python $V install --timeout 20 --retries 0 -c "$D/constraints.txt" durabletask==1.12.0 agent-framework-core==1.24.0 agent-framework-durabletask==1.0.0b261029 openai==3.38.0 types-grpcio==1.84.0.20261021
python -m pip --python $V install --no-compile --timeout 20 --retries 0 -c "$D/constraints.txt" "$D/opentelemetry_instrumentation_langchain-0.63.0-py3-none-any.whl" "$D/opentelemetry_instrumentation_weaviate-0.63.0-py3-none-any.whl" chainlit==2.12.0 python-dotenv==1.2.2 'fastapi>=0.137.1' 'pydantic>=2.14.1,<3.0' httpx==0.28.1 'PyJWT[crypto]>=2.15.0,<3.0.0' uvicorn==0.54.0 itsdangerous==2.2.0 tenacity==9.1.4
python -m pip --python $V install --no-compile --timeout 20 --retries 0 -c "$D/constraints.txt" azure-identity==1.25.3 azure-appconfiguration==1.10.0 azure-cosmos==4.5.1 azure-monitor-opentelemetry==1.8.9 azure-monitor-opentelemetry-exporter==1.0.0b55 azure-storage-blob==12.30.0 msal==1.35.1 opentelemetry-instrumentation-httpx==0.64b0 azure-appconfiguration-provider==2.5.0 azure-applicationinsights==0.1.1
# Reconcile the overlapping graph, not a full requirements-file download retry:
python -m pip --python $V install --no-compile --timeout 20 --retries 0 -c "$D/constraints.txt" "$D/opentelemetry_instrumentation_langchain-0.63.0-py3-none-any.whl" "$D/opentelemetry_instrumentation_weaviate-0.63.0-py3-none-any.whl" chainlit==2.12.0 'fastapi>=0.137.1' azure-monitor-opentelemetry==1.8.9 opentelemetry-instrumentation-httpx==0.64b0
python -m pip --python $V uninstall -y opentelemetry-exporter-otlp-common opentelemetry-exporter-http-transport
python -m pip --python $V check
```

Browser testing installed **Playwright 1.61.0**, matching the already available
test-tool version, into this venv with normal dependencies. Existing Chromium
was reused; no browser install, system package overlay or production auth change.

### Focused qualification and actual screenshots

| Boundary | Actual result |
| --- | --- |
| UI declared setuptools 84.1.0 wheel | Build passed; all three schema/hash pairs match exact source/reviewed bytes. Artifact `$env:TEMP/inline-declared-ui-wheel-ap3k0mjm/gpt_rag_ui-3.5.0-py3-none-any.whl` |
| ORCH existing isolated hosted venv | All six actual pyproject base declarations plus hosted SDK match; pip check clean. Focused config/snapshot selectors: **12 passed, 27 deselected, 13.74s** |
| ORCH declared Hatchling backend (1.32.4; declaration is unpinned) | Wheel built; exact three declared inline-schema force-includes, sibling hashes and VERSION verified. Artifact `$env:TEMP/inline-declared-orch-wheel-lit234zr/gpt_rag_orchestrator-0.1.0-py3-none-any.whl` |
| UI reader suite under complete declared graph | **17 passed, 3.422s**, no skips |
| UI actual handler-focused suite | **4 passed, 0.739s**: text-only projection/owner binding, admitted envelope element, construction-failure readable fallback, admitted history citations |
| UI actual installed 2.12 JSX runner smoke | **1 passed, 30.522s**; existing four standalone/iframe/theme combinations and eleven scenarios, exact values, controls, wide-data bounds and no external renderer requests |
| Actual synthetic Chainlit 2.12 app/capture | Exit 0; real light/dark pages returned 200, with one card, two tables, one SVG, sort/filter checks and no renderer/page errors |

The JSX browser test first failed on its hardcoded 2.9 minifier variable names.
Only `UI/tests/test_inline_presentation_browser.py` changed: structural runner
matching now tolerates renamed local arguments. No runner/library/SDK,
production source, authentication, CSS or JSX was patched. Ruff and targeted
diff check pass. Tested harness SHA-256:
`a83cf5d988bdd12e35ded0184da44a4c4e5f6dc82564da17180161d4b6f1e181`.

Commands from the UI root:

```powershell
$env:PYTHONPATH = 'src;tests'
& $V -m unittest discover -s tests -p test_inline_presentation.py -q
& $V -m unittest test_native_presentation.NativePresentationTests.test_text_only_handler_uses_shared_readable_projection_without_visual_elements test_native_presentation.NativePresentationTests.test_admitted_assistant_envelope_displays_exact_fallback_and_shared_element test_native_presentation.NativePresentationTests.test_element_construction_failure_keeps_authorized_readable_answer test_native_presentation.NativePresentationTests.test_history_citations_preserved_only_in_admitted_assistant_messages -q
& $V -m unittest discover -s tests -p test_inline_presentation_browser.py -q
Set-Location .artifacts/actual-chainlit
$env:CHAINLIT_APP_ROOT = (Get-Location).Path
$env:CHAINLIT_ENV_FILE = 'nonexistent-local-test.env'
$env:PYTHONPATH = "$UI/src"
# Attached local helper; stop its exact session after the capture.
& $V -m chainlit run app.py --host 127.0.0.1 --port 8765 --headless
# In a separate shell with the same explicit interpreter:
& $V capture.py
```

Actual 2.12 artifacts are `UI/.artifacts/actual-chainlit/evidence.json`,
`chat-light-desktop.png` and `chat-dark-desktop.png`; prior 2.9.4 screenshots
and receipt were preserved in `prior-chainlit-2.9.4/`.
Screenshot SHA-256: light
`4d5ecdb537bd97db77e26dfcc9fec22b5654b3f2449c1e70fa6d14bd44b639a3`;
dark `cd579869814cb0814e747b5b1894d8a05e2eb3ebee9e7d9e54309d5e62c717d4`.
The actual app shell attempted external KaTeX CSS; the capture blocked it,
and no external resource was fetched. The visual renderer itself issued no
external requests in the separate browser smoke. Synthetic fixtures only.
The attached loopback server was stopped and port 8765 was verified closed.
No screenshots/comments were uploaded; approval remains outstanding.

These are current feature-source/package results, **not** manifest-pinned
UI v3.6.0/ORCH v7.1.0 release-binary composition, full quality, all optional
ORCH host/tool profiles, authenticated embedding, Azure or live/human
certification. Manifest, requirements/pyproject pins, provider source, locks,
hooks, auth and private environments remain unchanged.

## Local implementation evidence — 2026-11-07

T001 is explicitly approved for local implementation by the user's message
“autorizo a trafa 1 t001”; see ADR-0040. This does not open live or release gates.

Inventory used local repository directory listings, Git remotes, status, refs
and registered worktrees; no app-list tool was exposed in this session. Shared
checkouts were not switched. Initial inventory performed no network operation.
Later narrowly authorized missing-dependency installation attempts failed
securely; no Azure operation, workflow, commit, push or publication occurred.

| Checkout | Actual source baseline and state |
| --- | --- |
| Current umbrella `placerda-fantastic-spork` | `feature/inline-visual-output`, `0d755e8`; existing untracked ADR/spec artifacts retained |
| `C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\gpt-rag-orchestrator\inline-visual-output` | Isolated feature worktree from local `origin/develop`, `59f2de72b07f3b8e182e6afabdcf24a056886ef3`; uncommitted runtime/contracts/tests/package edits |
| `C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\gpt-rag-ui\inline-visual-output` | Isolated feature worktree from local `origin/develop`, `a1e0979c3389526c4483c43dabec4e660519ad57`; uncommitted reader/handlers/renderer/contracts/tests/package edits |
| Central docs `C:\Users\paulolacerda\.copilot\repos\ai-landing-zones` | `main`, `d397635`, shared dirty checkout left untouched |
| Central docs isolated `C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\ai-landing-zones\inline-visual-output` | `feature/inline-visual-output-docs`, `4cf3b3c099bd00021e99e57ff9a750d043eded0e`; untracked unshipped coordination draft |

These local develop refs are older than the design baselines and are not a
validated combination. Actual UI native API paths are
`src/gpt_rag_ui/api/native.py` and `src/gpt_rag_ui/api/native_chat.py`, not root
`api/`. Orchestrator has `src/native/`; this local baseline lacks the proposed
`knowledge.py`; public capture instead belongs in `presentation_middleware.py`.
UI reader lives in `services/native_presentation.py`; tests use existing
`tests/` collection. No runtime-access blocker is asserted.

Local changes: three root schemas and sibling hashes retain design bytes;
seven synthetic examples are under `contracts/examples/inline-presentation/`.
The settings validator rejects duplicate/nonfinite JSON, unsupported shapes/
versions, duplicate rule IDs, empty and overlapping exact numeric intervals.
Shared resolution and publication require `agent-lz`/`text/plain` and return
compact JSON. Missing settings add no declaration or resource.

Validation actually run:

- New contract tests before promotion: 4 failed (missing root schemas), 1 passed;
  after promotion: 5 passed.
- New publication cases before implementation: 7 failed; new provider adapter
  cases before shared merge validation: 8 failed.
- `python -m pytest tests/test_presentation_contracts.py tests/test_presentation_settings.py tests/test_appconfig_intent.py tests/test_app_settings_resolution.py tests/test_native_application.py -q`:
  **218 passed in 5.87 seconds**.
- A combined run additionally including `tests/test_infra_provider_hooks.py`
  was stopped after repeated 120-second waits; it is **not** a passing hook
  result. No hook source changed.
- `git --no-pager diff --check`: passed.

Provider assessment is bidirectional: both composition adapters use the same
`app_settings.py` merge, tested with identical compact value/metadata and
absent/default behavior. Neither Bicep nor Terraform foundation source needs a
new resource/input; both already transport the generic settings collection.
PowerShell/shell hooks remain unchanged and use shared publication. This is
offline adapter evidence only, not full provider/hook or deployed parity.
Existing ignore rules retain Terraform locks and exclude private state/inputs;
root contract attributes enforce LF. No generic ignore additions were made.

The preceding 218-test receipt is retained for unchanged foundation files;
the latest component/package/browser receipts below supersede foundation-only
status. Residual gaps include complete native lifecycle and channel matrices,
reconciliation/hook evidence, declared-pin
composition and full quality. T054-T058 remain blocked/pending: no approved
dedicated target and no actual host/operator/analyst acceptance. Existing proof
is not new runtime evidence. Manifest pins are unchanged. Reader-first rollout
and disable-production/retain-readers rollback remain requirements, not executed
operations.

## T002/T027 continuation receipt — 2026-11-08

**Current local status**: T002, T003, T020, T021, T025, T026 and T027 are
complete. This receipt supersedes the initial missing-tool/module and inventory
blockers below; historical failures remain attributed to their original runs.
No production-hook or provider source fix was needed in this continuation.
Full declared-pin runtime/UI qualification, shipped documentation and
live/human acceptance are still separate, unfulfilled gates.

### T002 — exact known-file inventory

All four isolated worktrees are accessible at the paths in the baseline table.
ORCH/UI `git merge-base --is-ancestor origin/develop HEAD` both exit 0; neither
shared checkout was switched. Actual HEADs are recorded above, not manifest
release commits. `ALZ/manifest.json` still declares:

| Declared component | Version/tag | Commit |
| --- | --- | --- |
| Umbrella | v7.2.1 | Actual feature HEAD `0d755e8da296a9e88e1397cc81bdb43428e28367`, not a newly released combination |
| ORCH | v7.1.0 | `666d39862590cfb165097ee55737a1ef66fd2afc` |
| UI | v3.6.0 | `8a45595aa321d8841e7a4555d542b890beebf1b0` |
| Ingestion | v3.1.3 | `d7f34eb040cc308ce18d0d95ee9c9cb0f07028b1` |
| MCP | v2.0.0 | `e462d929ce02a74813feff9288d155098295691c` |
| Bicep provenance (`infra.source`) | v2.7.3 | `97e2375b89dcda4900d75aac9e7ffb7b20cce165` |

The older develop-based ORCH/UI feature baselines are **not** qualification of
these manifest pins. Ingestion/MCP/private demos were not inspected.

Instruction inventory: ALZ, ORCH and UI each have root `AGENTS.md` and
`.github/copilot-instructions.md`. ALZ's owning scopes are
`.github/instructions/config-python.instructions.md` for the publisher,
`contracts.instructions.md` for root contracts,
`infrastructure.instructions.md` for provider validation,
`lifecycle-hooks.instructions.md` for traced hook surfaces, and
`release.instructions.md` for changelog/manifest surfaces. ORCH's changed
`tests/**/*.py` match `.github/instructions/tests.instructions.md`; its
`contracts/**` match `contracts.instructions.md`. Existing API, connector and
strategy scopes target `src/api`, `src/connectors`/plugins and
`src/strategies`/orchestration respectively, not `src/native`. UI's changed
Python/tests match `.github/instructions/python.instructions.md`; canonical
API files also match `authentication.instructions.md`, while presentation
assets match `frontend.instructions.md`. Backend-client and persistence
scopes were inventoried at `backend-clients.instructions.md` and
`persistence.instructions.md`; neither introduces a new native test runner.
The existing DOCS feature checkout has no root AGENTS/copilot/scoped instruction
set; central docs ownership remains `docs/agent-landing-zone` and `mkdocs.yml`.
Applicable existing `engineering-principles`, `documentation-consistency` and
`speckit-implement` skills were read. No extension hooks/new planning files.

| Owner and actual imports | Canonical source / collected tests / package |
| --- | --- |
| ORCH `src/native/agent.py` imports public `Agent`, `AgentContext`, `agent_middleware`, `FoundryChatClient`, local `FunctionalSnapshot`/`NativeConfig`, `AGENT_NAME`, `ToolIdentity`/`compose_tools`, presentation settings and capture/composition middleware | `src/native/config.py`, `presentation.py`, `presentation_middleware.py`; collected `tests/test_native_presentation.py`, `test_native_presentation_config.py`, `test_native_runtime.py`, `test_native_multi_agent_presentation.py`. No proposed `knowledge.py` at this baseline |
| UI `src/gpt_rag_ui/api/native_chat.py` imports shared `presentations`/`text_projection`, typed `NativeService`/`NativePrincipal`, citations, existing auth/config, Hosted client and lazy durable client | `src/gpt_rag_ui/services/native_presentation.py`, `services/native.py`, `api/native.py` (`rest_projection`), `api/native_chat.py`; `public/elements/Presentation.jsx`; collected `tests/test_inline_presentation.py`, `test_native_presentation.py`, `test_inline_presentation_browser.py`, `test_inline_chainlit_browser.py`. No root `api/test_native_presentation_*.py` |
| ALZ shared declaration/resolution/publication | `config/deployment/app_settings.py`, `appconfig_intent.py`, `appconfig.py`; `tests/test_presentation_contracts.py`, `test_presentation_settings.py`, `test_app_settings_resolution.py`, `test_appconfig_intent.py`, `test_native_application.py`, `test_infra_provider_hooks.py`; callers `scripts/preDeploy.ps1`, `scripts/preDeploy.sh` |
| Matched schema distribution | ALZ `contracts/` owns the three schemas and sibling SHA metadata. ORCH `pyproject.toml` Hatchling force-includes them into wheel `native/contracts`; loader uses repository contracts then packaged fallback. UI setuptools `pyproject.toml` packages `src/gpt_rag_ui/contracts/*.json` and `*.sha256`; reader resolves that package directory. No UI MANIFEST.in or new schema package |

ORCH pytest collection is configured in `pyproject.toml`: `pythonpath=["src"]`,
`testpaths=["tests"]`, `asyncio_mode="auto"`. Its
`.github/workflows/pr_pipeline.yaml` uses Python 3.12 and
`pytest -q --junitxml=.artifacts/pytest.xml`. UI uses
`.github/workflows/tests.yml` (not `pr_pipeline.yaml`) and protected
`.github/scripts/run-unittest.py --base-ref "$BASE_SHA" --report .artifacts/unittest.json`.
Focused local collection uses the unittest commands/bootstrap below.
ORCH uses its declared Hatchling backend; UI declares setuptools **84.1.0**.
Existing available-backend wheel/hash evidence below is not declared-backend
or declared Chainlit-version qualification; those residual blockers are not
silently promoted by this infrastructure restoration.

ALZ `.github/workflows/infra-validate.yml` pins Terraform 1.13.0 and Bicep
0.42.1; it runs fmt, readonly/backend-disabled init, validate, tests, pytest,
Bicep build/lint and `infra/tests/Invoke-OfflineContracts.ps1`. Its Azure-CLI
compiler installation and what-if lanes were **not** executed locally.
Use the standalone session compiler and mocked selector below; do not run
the whole workflow or Azure-dependent wrappers under this local authorization.

DOCS `.github/workflows/docs-build-check.yml` uses Python 3.11 and
`requirements-docs.txt`/`requirements-planner-tests.txt` dependencies. Its
existing preparation is `pip install -r requirements-docs.txt -r requirements-planner-tests.txt`
and `python -m playwright install --with-deps chromium`; neither was run in
this continuation. Existing build-only commands,
from the DOCS root, are:

```powershell
python scripts/planner/validate_catalog.py
python -m unittest discover -s tests/planner -p "test_*.py"
mkdocs build --strict
python tests/planner/browser_checks.py
python tests/home/browser_checks.py
```

These are inventory, **not new passing doc-build evidence**. The deploy workflow
adds `gh-deploy`, which is unauthorized. Exact `mkdocs.yml` page references
remain listed in the initial receipt below. Only the existing unshipped
`DOCS/drafts/agent-landing-zone/inline-visual-output.md` was updated; T059
shipped-page/nav delivery is still open.

### T027 — exact tools, narrow offline checks and non-impact

One HTTPS-only download from the declared public Bicep release succeeded.
Session executable: `$env:TEMP/inline-us2-tools-20261108/bicep-0.42.1.exe`;
version `Bicep CLI version 0.42.1 (caea9302e8)`;
SHA-256 `dde63bab0d12da761cb75708d53d024a59c5f91a13a883d3e06c4ba951ee50f9`.
Shared Bicep 0.37.4 was not replaced.

```powershell
$exe = Join-Path $env:TEMP 'inline-us2-tools-20261108/bicep-0.42.1.exe'
# Initial download only: directory was created in session temp, not the repo.
curl.exe --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --connect-timeout 15 --max-time 90 --output $exe https://github.com/Azure/bicep/releases/download/v0.42.1/bicep-win-x64.exe
& $exe --version
Get-FileHash $exe -Algorithm SHA256
$compiled = & $exe build infra/bicep/main.bicep --no-restore --stdout
& $exe lint infra/bicep/main.bicep --no-restore
Set-Location infra/terraform
$env:TF_IN_AUTOMATION = 'true'
$env:TF_INPUT = '0'
$env:TF_REGISTRY_CLIENT_TIMEOUT = '15'
$env:TF_REGISTRY_DISCOVERY_RETRY = '0'
terraform init -backend=false -lockfile=readonly -no-color
terraform validate -no-color
terraform test '-filter=tests\services.tftest.hcl' '-no-color'
```

Pinned Bicep build and lint: **exit 0**, generated template retained in memory,
no repository output. Existing BCP053/BCP318 and linter/type/dependency warnings
remain. Terraform init: **exit 0**, current explicitly pinned public modules
restored (including App Configuration 0.5.1, Key Vault 0.10.2, PostgreSQL 0.2.3
and pinned network/transitive AVM modules), signed locked providers installed:
azapi 2.13.0, azurerm 4.81.0, modtm 0.4.0, random 3.9.1, time 0.14.2.
No backend initialized. Validate: **exit 0**.
Services file: **26 passed, 0 failed**; all providers mocked and all run commands
are plan, so no real Azure provider resources/auth/API calls.
Existing deprecation/randomization and targeted-fixture warnings remain.
`terraform test -filter=tests/services.tftest.hcl -no-color` first selected
**0 tests**, exit 1 on Windows; the native backslash selector above is required.

Terraform lock SHA-256 remains
`43c0975f87920c17d301968a28b4563524929e3ab7d8602b49211d1b938a2421`;
worktree/HEAD lock Git blobs both
`bc827e21b52c25a0f81fbe39451649a192b66ec2`. No manifest/module pin/provenance,
foundation/provider or production-hook edits; local ignored `.terraform`
dependency cache only. The initial shared 109-test and affected 9-test hook
receipts below remain the relevant passing behavioral evidence, not reruns.

**Final bounded old-hook diagnosis**: one exact fully mocked pre-provision
case, not a real lifecycle or broad hook suite:

```powershell
@'
import subprocess, time, pytest
original = subprocess.run
def bounded(*args, **kwargs):
    kwargs['timeout'] = min(kwargs.get('timeout', 45), 45)
    start = time.monotonic()
    result = original(*args, **kwargs)
    if isinstance(args[0], list) and args[0][-1].endswith('wrapper.ps1'):
        print('Exact mocked hook elapsed:', round(time.monotonic()-start, 2), 'exit:', result.returncode)
    return result
subprocess.run = bounded
raise SystemExit(pytest.main(['tests/test_infra_provider_hooks.py::test_complete_hook_prepares_selected_inputs_and_short_circuits[terraform-infra/foundation-foundation-none-pwsh]', '-q', '--tb=short', '-s']))
'@ | python -
```

At a preceding 30s cap, timeout occurred in 31.07s after all trace events:
selection-validation, appdefinition, terraform_groups, topology, firewall,
mcp-capture, inputs, environment-reload, postgresql, egress,
regional-preflight, foundation-preflight. Final 45s bound: subprocess
**28.56s, exit 0; 1 passed in 28.81s**. Synthetic mocked boundaries only.
This resolves the selected test-lane gap, not a proven production root cause
or certification of all 77 hook cases. No production hook changed.

**CSS attribution correction**: UI full dirty diff warnings on
`public/custom.css` lines 99–199 are specifically the prior 101-line
inline-presentation addition (theme tokens/table/cards/chart controls).
They are tightly coupled presentation line-ending/trailing-whitespace cleanup,
not unrelated legacy CSS. This continuation did not edit/normalize that asset;
changed Python test diffs pass. Preserve this known formatting follow-up
separately from T027's provider/tool result.

## Initial local US2 reconciliation receipt — 2026-11-08 (historical)

At this initial checkpoint T020, T021, T025 and T026 were complete; T027 was
blocked and T002 partial. The continuation receipt above resolves those two
blockers; T003's existing inventory remains valid. No new
repository/vendor/doc-page research was performed in this initial increment.
Existing baseline/packaging/schema/domain/CI evidence
above and below is retained, not relabeled as a new full-suite run.
The read-only requirements checklist remains 16/16 checked; no extension hooks
were configured. This work adds no planning artifact, installs no dependencies
and performs no Azure API/CLI query, login, commit, push, upload or publication.

**Actual fix**: `prepare_publication` now defaults only the ordinary presentation
key to compact `{"schemaVersion":1,"agents":{}}` at `agent-lz`/`text/plain`.
Explicit valid settings still win. Omitted declarations no longer leave a stale
enabled value. Existing generic provider inputs remain absent when unconfigured;
the runtime lifecycle writer performs the empty-map convergence without a
new input/resource, key enumeration/deletion or auth removal. This is a deliberate
runtime write, not a claim that omission produces no App Configuration write.
Both unchanged pre-deploy hooks invoke `config.deployment.appconfig` after
`native_deploy`, with `--require-hosted-endpoint`, before component deployment.
Shared CLI resolution/validation/writing supplies identical behavior for both
providers. The CLI regression exercises enable → remove/empty/off → repeat with
the actual `_run_az` boundary mocked; other-label and auth values survive.

| Changed boundary / test mapping | Actual result |
| --- | --- |
| ALZ `appconfig_intent.py`, `test_appconfig_intent.py`, `test_app_settings_resolution.py` | New removal case first failed (1 failed, 36 deselected, 0.96s); after fix, 109 passed in 4.56s, including both adapter variants and CLI validation/metadata/default/convergence cases |
| ALZ `test_infra_provider_hooks.py` | 8 new affected lifecycle block cases plus existing stdin-helper case: 9 passed, 68 deselected, 5.76s; pwsh/bash × Bicep/Terraform × success/failure blocks, each subprocess bounded at 10s |
| ORCH `tests/test_native_presentation_config.py` plus existing scoped/snapshot/secret selectors in `test_native_runtime.py` | 12 passed, 27 deselected, 5.00s; public SDK enabled/disabled source counts, no disabled normalization/selection, stable-ID isolation, invalid-present actionable errors, actual next-turn removal while cached refresh is inert, JSON-restored immutable workflow snapshot and live auth/MCP |
| UI `tests/test_inline_presentation.py` | 17 passed in 2.824s; exact readable narration/fallback for Hosted `output/content` and `messages/contents`, optional REST fields, future version and pending/completed/nonvisual workflow cases |
| UI `NativePresentationTests.test_text_only_handler_uses_shared_readable_projection_without_visual_elements` | 1 passed in 0.495s; actual `native_chat.text_output`/`display_output`, owner binding retained, no element/message creation; completed JSON result remains readable |
| Bicep `main.bicep` | Offline `build --no-restore --stdout` exit 0; compiled generic `additionalAppConfigurationSettings` parameter present. Existing compiler warnings remain. Available CLI is **0.37.4**, not the specified 0.42.1; this is not pinned-compiler acceptance |
| Terraform | `fmt -check -recursive` exit 0 with 1.13.0; `validate -no-color` exit 1, missing installed modules (and consequent provider type mismatch diagnostics). No `.terraform` in this worktree; no offline init/module/provider cache established. Init/validate/test remain unfulfilled, no network init attempted |

Exact new/focused commands from the umbrella:

```powershell
python -m pytest tests/test_app_settings_resolution.py tests/test_appconfig_intent.py -q
python -m pytest tests/test_infra_provider_hooks.py -q -k 'predeploy_presentation or powershell_python_module_receives_json_through_stdin'
$compiled = & bicep build infra/bicep/main.bicep --no-restore --stdout
# Exit 0; parse captured JSON, do not save generated templates to source.
Set-Location infra/terraform
terraform fmt -check -recursive
terraform validate -no-color
```

ORCH uses the existing `$ORCH`/`$NATIVE` paths in “Reproducible latest local
commands” (prepared hosted environment, no dependency/pin change):

```powershell
Set-Location $ORCH
$env:PYTHONPATH = 'src;tests'
& $NATIVE -m pytest tests/test_native_presentation_config.py tests/test_native_runtime.py -q -k 'presentation_config or scoped_selectors or snapshot or secrets' --maxfail=1
python -m ruff check tests/test_native_presentation_config.py
```

UI reader command: `python -m unittest discover -s tests -p
test_inline_presentation.py -q` with `PYTHONPATH=src` in `$UI`.
For the handler, reuse the existing compatible-package bootstrap in
“Reproducible latest local commands”, replacing its suite construction with:

```python
suite = unittest.TestSuite([NativePresentationTests(
    'test_text_only_handler_uses_shared_readable_projection_without_visual_elements')])
r = unittest.TextTestRunner().run(suite)
sys.exit(not r.wasSuccessful())
```

`python -m ruff check tests/test_native_presentation.py
tests/test_inline_presentation.py` passes. Umbrella, ORCH and docs
`git --no-pager diff --check` pass. UI full dirty-tree diff check reports
existing `public/custom.css` line-ending/trailing-whitespace warnings
(lines 99–199). Later attribution confirms this is the previous presentation
addition, not unrelated legacy CSS; it was not edited or normalized here.

**Bounded old-hook diagnosis**: the stdin helper alone passes (2.61s). One
existing full Terraform/PowerShell pre-provision case was run with its
`subprocess.run` timeout capped to 15s instead of 120s:

```powershell
@'
import subprocess, pytest
original = subprocess.run
def bounded(*args, **kwargs):
    kwargs['timeout'] = min(kwargs.get('timeout', 15), 15)
    return original(*args, **kwargs)
subprocess.run = bounded
raise SystemExit(pytest.main(['tests/test_infra_provider_hooks.py::test_complete_hook_prepares_selected_inputs_and_short_circuits[terraform-infra/foundation-foundation-none-pwsh]', '-q', '--tb=short']))
'@ | python -
```

Result: timeout/failure in 17.26s. Mock trace: selection-validation,
appdefinition, terraform_groups, topology, firewall; the private synthetic
snapshot had persisted `ORCHESTRATION_HOST` but not later topology/firewall
values. Thus the bounded run stopped during/after persistence and before MCP
capture, not in presentation publication. This establishes a bounded residual
test-lane gap, not a production-hook root cause. No matching child process
remained after termination. Do not rerun the entire 77-case hook suite or
wait indefinitely; new affected pre-deploy selectors pass independently.

**Source attribution**: same feature baselines as the inventory; work remains
uncommitted. SHA-256 of the tested changed files:

| File | SHA-256 |
| --- | --- |
| ALZ `config/deployment/appconfig_intent.py` | `459cceda77870a9cf137076ead190ac458d54a26deb6a1b654c4bca65ef3344b` |
| ALZ `tests/test_appconfig_intent.py` | `6191b95573bdd0f885fcaa77a4cf1ac185b086752042586614e1ddc577430548` |
| ALZ `tests/test_app_settings_resolution.py` | `d1f1de51293baac0b950afef7398c1542791a98aa9ed30aeef29beefc4cb6477` |
| ALZ `tests/test_infra_provider_hooks.py` | `30f81ccc4cfa0c6bcad94061d52722256c55fd71c309217c26fcf3325898f1be` |
| ORCH `tests/test_native_presentation_config.py` | `98bd869d08a6f7fbf99102268b266f9a051a022e829e28162ac7929338dbf7bc` |
| UI `tests/test_inline_presentation.py` | `697d2a1777191bd8d283274abe6f2e8eab957b6ed8a3e762caf945eb3a2cb6ea` |
| UI `tests/test_native_presentation.py` | `8b77851192ded73411a6d205c563cae0c538e9e487e13be73f6bc3b67c69e1e3` |

Manifest, foundation source, Terraform lock/module pins, Bicep provenance,
contracts and runtime/UI implementation files remain unchanged in this
increment (only the shared publisher required a code fix). The earlier 218
foundation receipt is reused for unaffected schemas/validators/native
composition; changed configuration tests were rerun, not claimed unchanged.
No cross-repository release combination is certified. Reader-first integration,
disable production/retain readers rollback and exact future manifest binding
remain delivery requirements.

Central docs feature branch retains the unshipped
`drafts/agent-landing-zone/inline-visual-output.md`, updated with this convergence
and offline evidence. No current shipped page/navigation was changed. Existing
navigation inventory in `research.md` identifies these exact registered pages
under `DOCS/docs/agent-landing-zone/`, through `DOCS/mkdocs.yml`:
`application.md`, `hosted-agents.md`, `agent-strategies.md`, `workflows.md`,
`conversations.md`, `embed-chat.md`, `application-settings.md`,
`configuration.md`, `application-api.md`, `application-testing.md`,
`operations.md`, `application-monitoring.md`, `agentops.md`,
`publish-to-teams.md`, and `connect-copilot-studio.md`. This satisfies T003's
navigation/reference inventory for native agents, configuration, workflows,
history, embed and customer APIs without new research. Fixture domains,
contract hashes/revisions, local/live/final lanes and target approval are in
the retained inventory; changed-boundary test mapping/hashes are above.
Full page-content inventory/update is still a delivery obligation.
T002 is not marked complete from partial instruction/import/command inventory.
T027 still needs the
pinned Bicep check and prepared offline Terraform dependencies/validation;
T056 and other live/human gates still need dedicated target approval.

## Prerequisites and scope

- Umbrella feature branch: `feature/inline-visual-output`, targeting `develop`.
- Use the manifest-pinned UI/orchestrator as the source baseline, then matched feature branches from `develop` for implementation. Record actual tested revisions, do not invent future tags.
- Python 3.12 in isolated component environments. UI and orchestrator declare >=3.12. Use each repository's tracked requirements and quality tools, restoring dependencies only when missing.
- JSON Schema Draft 2020-12 support. Current planning environment has `jsonschema` 4.26.0.
- Bicep v0.42.1, Terraform 1.13.0 and PowerShell for existing umbrella checks. Run shell-hook checks on Linux/CI as well.
- Acceptance is local-only: no Azure target, live smoke or deployed provider
  exercise is required or authorized. Do not reuse stopped proof compute or
  provision resources. Azure behavior is unverified residual risk, not a blocker.
- Azure/demo inspection, traffic, configuration, data access, deployment,
  restart and cleanup are off-limits. Do not persist private target identities.

Read [data-model.md](data-model.md) and the [contracts](contracts/README.md) for payload/configuration semantics. The [minimum proof](feasibility.md) establishes only the standard Hosted carrier/history subset. Its `inline_visual_proof` marker differs from the proposed product contract.

No NL2SQL installation or other named integration is a prerequisite. Use authorized typed outputs from user-selected tools, including a customer-defined tool, through [the shared structural normalization path](contracts/tool-results.md). Synthetic source fixtures are transport/contract inputs, not an assertion that arbitrary tool output is automatically eligible.

## Minimum-work route

Default to the local lane. Do not run every command and acceptance scenario in this guide after every edit.

| Lane | When and minimum work |
| --- | --- |
| Local iteration | Run changed-boundary tests with synthetic results, fixed selection and deterministic clocks. Cover disabled behavior, valid output and relevant negatives without Azure/model/tool calls. Reuse installed dependencies and combine related selectors in one runner. |
| Configuration/provider checks | Only when publication, providers or hooks are affected, run the relevant shared/Bicep/Terraform and PowerShell/shell checks below. For runtime/UI-only edits, document non-impact and retain unchanged infrastructure evidence. No provisioning in this lane. |
| Local candidate acceptance | Complete section 4 and the controlled SDK/history/Playwright matrix once. Repeat invalidated cases with exact source attribution. Required CI remains mandatory. |

Keep 20 distinct controlled histories, 20 local multi-agent runs, 30 measured
renders and automated browser/provider checks for final acceptance,
not each iteration.
Use local fixture publication and controlled lifecycle boundaries; they do not
establish deployed parity or Azure persistence/ACL enforcement.

Record source/contract hashes, dependencies, settings and local boundary
assumptions for reused evidence. Recheck changed schema/SDK/auth/history/renderer/
publication boundaries. Never relabel old source-sealed reports as new runs.
Missing Azure targets are not an acceptance gap or a provisioning request.

Use only selectors and deployment/configuration entrypoints supported by the actual owning checkout. The commands below are known entrypoints, not a requirement to run full component/foundation suites locally every time. Record elapsed times to identify bottlenecks; no unmeasured end-to-end duration is promised.

## 1. Draft contract sanity checks, runnable now

From the umbrella root, use the existing JSON Schema package:

```powershell
@'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
root = Path("specs") / "005-inline-visual-output" / "contracts"
pairs = [("turn-presentation-v1", "presentation"),
         ("presentation-selection-v1", "selection"),
         ("agent-presentation-settings-v1", "settings")]
for name, fixture in pairs:
    schema = json.loads((root / (name + ".schema.json")).read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for suffix in ("valid", "invalid"):
        value = json.loads((root / "examples" / (fixture + "-" + suffix + ".json")).read_text())
        errors = list(validator.iter_errors(value))
        assert bool(errors) == (suffix == "invalid"), (name, suffix, errors)
print("Three schemas and six positive/negative fixtures pass.")
'@ | python -
```

Expected: all three schemas are valid, positive fixtures pass, negative fixtures fail. Check sibling `.sha256` metadata against exact schema bytes. This does not test source ownership, rule overlap, cross-column typing, aggregate limits or a renderer.

`source-fixture.json` is the synthetic authorized source registry. Sales fixtures match the provided selection/presentation. Operations and finance cover source statuses, nulls, and precision beyond JavaScript's safe integer range.

## 2. Existing umbrella regression commands

Run the relevant cases after related configuration/hook code exists, using the minimum-work route above:

```powershell
python -m pytest tests\test_app_settings_resolution.py tests\test_appconfig_intent.py tests\test_native_application.py tests\test_infra_provider_hooks.py --quiet
pwsh -NoProfile -File .\infra\tests\Invoke-OfflineContracts.ps1
```

The existing `.github\workflows\infra-validate.yml` also runs `python -m pytest tests --quiet` on Windows/Linux and pinned Bicep restore/build/lint. Use that workflow for its real Bicep/provider prerequisites rather than inventing a new script.

From `infra\terraform`:

```powershell
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly
terraform validate
terraform test
```

Expected: no lock/module drift, both provider adapters retain matching settings/defaults and no new resources. Offline/mocked success is not deployed parity.

## 3. Existing component test entrypoints

**Orchestrator**, from its checkout, follows pinned `pr_pipeline.yaml`: host-specific `requirements-hosted.txt`, `requirements-container-apps.txt`, `requirements-tools.txt`, pytest/pytest-asyncio/pytest-mock/jsonschema, and tracked quality requirements. Once that isolated environment is available:

```powershell
python -m pip check
python -m pytest -q --junitxml=.artifacts/pytest.xml
```

**UI**, from its actual git checkout with a locally resolvable `origin/develop`, tracked runtime/quality requirements and the co-located tracked quality helper:

```powershell
$env:QUALITY_RUN_ID = "inline-visual-local-validation"
python .github\scripts\run-unittest.py --base-ref origin/develop --report .artifacts\unittest.json
```

This is the existing evidence-producing unittest runner, not a guessed pytest command. It seals source/test metadata and fails on tracked source changes during the run. Preserve its exit status/report. Add feature cases to the owning existing test suites during implementation, do not claim absent feature selectors run today.

## 4. Feature acceptance sequence, after implementation

This is the final **local-only** acceptance matrix. Run changed cases during
iteration and retain valid unchanged evidence; no actual-Azure smoke is included.

1. Validate settings/selection/source rules, strict shapes, malformed/unknown inputs and exact limit boundaries with synthetic fixtures. Enable only the configured stable native agent ID.
2. Exercise public function capture plus agent streaming/finalization. Compare the appended envelope in live updates and completed native output byte-for-byte. Assert no model measurement is accepted, no optional call for disabled agents, and unchanged consent/failure/cancellation handling.
   Run equivalent typed payloads under different native/MCP/customer-defined tool names through the same structural normalizer with a fixed selection/layout. Compare semantic values/shapes while permitting generated IDs/provenance names to differ. Test unstructured, ambiguous and lossy inputs for diagnosed text fallback; do not require a named remote integration.
   Start the stage timer after source/answer availability. Test before/at/after
   ten seconds, retries, slow processing and uncooperative cancellation using
   deterministic clocks and public SDK composition. Assert timely immutable
   text/output and safe diagnostics; no Azure integration is required.
3. Complete a controlled Hosted SDK turn, close the reader, and reopen through
   actual BFF admission code with native client I/O controlled locally and
   generation/source access disabled. Test wrong owners/arbitrary IDs and
   controlled deletion/access revocation. Do not fabricate an owner-denial result.
4. Repeat on public Durable state constructors/client interfaces and both typed
   workflow paths. Use fresh controlled clients/checkpoints, not a browser cache.
5. Exercise each block/chart variant, table sorting/filtering/copy, stable row follow-ups and suggestions in all four view/theme combinations. Assert one normal user message per activation, no direct tool or external visual request.
6. Repeat equivalent multi-agent workflows 20 times with randomized completion timing and two enabled/one disabled agent. Compare ownership, explicit workflow/occurrence ordinals and local block order.
7. Reopen 20 distinct controlled saved-history cases spanning legacy text,
   single/multi-agent and interrupted turns through fresh SDK/client interfaces.
   Compare values/citations/attribution/order with zero source calls, including
   after disablement; record individual local case IDs, not imaginary Azure IDs.
   Revoke original source access while retaining conversation access and verify the same historical snapshot access rules as text, with no new visual-history source ACL lookup. Preserve existing citation behavior. Verify that a subsequent row/suggestion query uses current permissions and fails closed where appropriate. Separately revoke conversation access and verify neither text nor visuals are exposed.
   Measure 30 complete-content renders on the documented reference device,
   including allowed content limits. Use the automated local provider/hook
   fixtures for default/opt-in/removal/repeated-publication and one-agent isolation.

Each rejected presentation must retain authorized readable text and record a safe rejection reason. Native authorization failures expose neither text nor visual content. Partial envelopes are not accepted visuals. Do not silently truncate or claim an empty success when a gate fails.

Include a primary-model response and user/tool content that imitate a schema-valid reserved presentation envelope. They must remain inert nonpresentation text in live and saved output; only the validated hydrator's envelope may render. Assert no arbitrary JSON/progress message bypasses source hydration.

## Requirement and outcome coverage

| Requirements | Evidence required |
| --- | --- |
| FR-001, FR-002, FR-021 | Per-agent empty/off defaults, guidance bounds, typed setting publication, fresh-turn snapshot, equivalent enable/disable/provider lifecycle |
| FR-003, FR-006, FR-011 | All four block families, bar/grouped-bar/line, units/tooltips/statuses, four view/theme combinations, keyboard/non-color meaning |
| FR-004, FR-005, FR-019 | Three-domain exact authorized values, shared differently named/customer-tool normalization, decimal/null fidelity, disjoint source/approved-rule indicators, no credential/source-owner crossing |
| FR-007, FR-008, FR-009 | Exact-value sort, filter/display-order copy, stable row identity after reorder, one normal-message activation and current authorization |
| FR-010, FR-014, FR-016, FR-017, FR-018, FR-020 | Fallback/new adapters, 10-second stage timeout including retries, cancellation/late-output exclusion, unknown version/block, independent invalid-unit rejection, whole-turn limit rejection, safe diagnostics/content/no egress |
| FR-012, FR-013 | Fresh native restore without queries/new source ACL checks, unchanged text-history rules after source revocation, current permissions for new actions, lifecycle/owner denial, 20 histories and 20 timing-varied multi-agent runs |
| FR-015, FR-022 | Published promoted schema/hash/examples, matched reader/runtime revisions, complete source sample and central current documentation |
| SC-001 | 100% value/indicator fidelity across sales, operations and finance and every supported family, equivalent differently named/customer-tool results without named-tool prerequisites |
| SC-002, SC-003 | Same interactions in four view/theme combinations and readable text in every rejection/unsupported/disabled/timeout case |
| SC-004, SC-005 | All 20 reopened histories and 20 repeated multi-agent runs preserve accepted content/order with zero disabled contributions or re-queries |
| SC-006 | Exactly/above: 10/11 blocks, 500/501 rows, 8/9 series, 1,000/1,001 non-null chart values, 262,144/262,145 compact UTF-8 envelope bytes |
| SC-007 | Additional generation completes or times out within 10 seconds per enabled agent including retries, with preserved text/other contributions and no late output; separately at least 95% of 30 complete-content renders readable within 1 second, documented device/dataset |
| SC-008 | Automated trend/critical-row reading and contextual follow-up assertions |
| SC-009 | Zero executable-content execution, visual-triggered external request or unauthorized disclosure, diagnosed rejection for all adversarial cases |
| SC-010 | Both provider/hook implementations achieve equivalent one-agent enable/disable/removal/repeated publication without changing other agents/auth |

Construct byte-boundary fixtures from valid envelopes using escaped inert text and multibyte Unicode, measuring the actual compact serialization including markdown/provenance, not character count or pretty-printed file size. Count chart gaps as null, not invented zero. Test above-limit aggregates across multiple valid contributions as well as individual blocks.

## Evidence and exit

Record actual HEADs plus dirty-source hashes, package versions/wheel hashes,
local controlled boundaries, settings/payload revisions, source counters,
diagnostics, browser network/security observations, exact limits, timings and
automated usability/provider outcomes. Image digests/publication/task-hub bindings are
**not available**, not invented or required Azure proof. A later separately
authorized release must bind actual artifacts under normal release rules.

A schema check alone is not full acceptance. Delivery requires the mapped local
SDK/history/Playwright behavior, local provider/hook parity, independent
measured rendering, automated usability checks, approved ADR and documentation.
Controlled finalization/history/auth failures block local completion; Azure
enforcement remains unverified residual risk, not future required proof.
No silent protocol/store/host-scope change or production/release approval exists.
# Latest bounded local validation

Component implementation is no longer foundation-only. The isolated ORCH
worktree has opt-in hydration/deadline/native-carrier production; UI has the
admitted projection and build-free renderer. Latest ORCH runtime/presentation
suite: **85 passing tests**. After adding fresh checkpoint-resume assertions,
the affected multi-agent module separately passed **22 tests**. These include
20 timing-varied actual public native workflow runs with two enabled stable
definitions, one disabled definition and a repeated enabled occurrence.
The existing research executor runs explicit producers sequentially; merged
order uses definition occurrence ordinals, never arrival time. Invalid/timed-out
producers retain valid siblings; aggregate overflow rejects all optional blocks.
Reviewed envelopes survive fresh checkpoint resume with no repeated source work.
No independent deployed agents or new scheduler are introduced.

Latest UI reader/actual JavaScript-helper suite: **14 passed**; actual native
handlers: **8 passed**. The latter crosses actual public function invocation,
capture/selection/hydration and NativeService/Chainlit handlers for enabled,
disabled, deadline and primary-marker-spoof cases. Model transport and native
state I/O remain controlled local boundaries. Public Durable state constructors
encode generated carriers in `$type: response/text` history entries with
`messageId`; fresh owner-admitted restoration makes no model/source calls.
Wrong owners fail before state reads. This does not prove real host persistence.

Contribution/source attribution and native replay dedup: **1 passed**.
Actual JSX/installed Chainlit runner/browser smoke: **1 passed in 8.648s**,
covering standalone/iframe × light/dark, bar/grouped-bar/line charts, exact
`9.750` clipboard text, in-flight duplicate activation suppression and zero
external requests/runner errors. It is not production secure-embed, complete
accessibility or performance/human acceptance.

The declared UI environment remains unavailable locally: installed Chainlit is
2.9.4 versus declared 2.12.0. One secure alternate install using existing
truststore/modern pip failed TLS at `files.pythonhosted.org`; no certificate
verification bypass or trusted-host was used. Composite existing-package tests
do not substitute for declared-pin composition. The declared UI wheel check
`python -m build --wheel --no-isolation` fails for missing setuptools==84.1.0.
An available-setuptools-75.8.0 wheel establishes schema inclusion only.
ORCH's existing Hatchling backend built its wheel. Both current wheels passed
exact LF/hash/archive and package-only import tests (**1 test**, 3.708s).
Scoped Ruff and all four `git diff --check` commands pass. Scoped mypy reports
three missing JSONSchema stub imports and one unavailable foundry-provider
import; it is not a passing full quality gate.

Central unshipped documentation draft is
`drafts/agent-landing-zone/inline-visual-output.md` in isolated
`ai-landing-zones/inline-visual-output`; published navigation is untouched.
T054–T058 still require separate dedicated-target/live/human authorization.

## Reproducible latest local commands

Run in the stated checkout; these commands do not contact Azure. Prepared
Python/package paths are session-local existing environments, not new pins.

```powershell
$ORCH = 'C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\gpt-rag-orchestrator\inline-visual-output'
$UI = 'C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\gpt-rag-ui\inline-visual-output'
$NATIVE = 'C:\Users\paulolacerda\.copilot\session-state\476dbbfa-6c86-4114-b531-3e685ea23877\files\native-maf-smoke\.venv-hosted\Scripts\python.exe'
Set-Location $ORCH
$env:PYTHONPATH = "src;$UI\src"
& $NATIVE -m pytest tests/test_native_runtime.py tests/test_native_presentation.py tests/test_native_presentation_multi_agent.py -q --maxfail=1
# 85 passed in 15.49s; after checkpoint assertion addition:
& $NATIVE -m pytest tests/test_native_presentation_multi_agent.py -q --maxfail=1
# 22 passed in 13.51s.
python -m ruff check src/native/agent.py src/native/config.py src/native/workflow.py src/native/presentation.py src/native/presentation_middleware.py tests/test_native_presentation.py tests/test_native_presentation_multi_agent.py
python -m mypy --follow-imports skip src/native/agent.py src/native/config.py src/native/workflow.py src/native/presentation.py src/native/presentation_middleware.py
# Ruff passes; mypy reports the four missing dependency/stub imports above.
```

Actual native-handler suite bootstrap (existing compatible Core/provider
packages imported before older global providers, while retaining installed
Chainlit). `INLINE_ORCH_TESTS=1` is required; otherwise the application-boundary
test intentionally skips and must not be claimed as executed.

```powershell
Set-Location $UI
$env:PYTHONPATH = "src;$ORCH\src;$ORCH\tests"
$env:INLINE_ORCH_TESTS = '1'
@'
import sys, unittest
import chainlit
p = r'C:/Users/paulolacerda/.copilot/session-state/476dbbfa-6c86-4114-b531-3e685ea23877/files/native-maf-smoke/.venv-published/Lib/site-packages'
sys.path.insert(0, p)
import agent_framework, agent_framework.openai, agent_framework_foundry, durabletask.client
sys.path.remove(p)
sys.path.append(p)
sys.path.insert(0, 'tests')
from test_native_presentation import NativePresentationTests
r = unittest.TextTestRunner().run(
    unittest.defaultTestLoader.loadTestsFromTestCase(NativePresentationTests))
sys.exit(not r.wasSuccessful())
'@ | python -
# 8 passed in 1.893s, including all four integration subcases.
python -m unittest discover -s tests -p test_inline_presentation.py -q
python -m unittest discover -s tests -p test_inline_presentation_multi_agent.py -q
python -m unittest discover -s tests -p test_inline_presentation_browser.py -q
# 14 / 1 / 1 passed. Browser uses existing Chromium and installed runner;
# all resources are locally fulfilled, no application server or model traffic.
python -m ruff check src/gpt_rag_ui/services/native.py src/gpt_rag_ui/services/native_presentation.py src/gpt_rag_ui/api/native_chat.py tests/test_native_presentation.py tests/test_inline_presentation_browser.py tests/test_inline_presentation_multi_agent.py
```

Current-source wheel/schema check (temporary wheel files, no release):

```powershell
Set-Location $ORCH
& $NATIVE -c 'import tempfile; from hatchling.build import build_wheel; print(build_wheel(tempfile.gettempdir()))'
Set-Location $UI
python -c 'import tempfile; from setuptools.build_meta import build_wheel; print(build_wheel(tempfile.gettempdir()))'
# UI uses available backend, NOT declared setuptools 84.1.0 qualification.
Set-Location 'C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\gpt-rag\placerda-fantastic-spork'
$env:INLINE_ORCH_WHEEL = Join-Path $env:TEMP 'gpt_rag_orchestrator-0.1.0-py3-none-any.whl'
$env:INLINE_UI_WHEEL = Join-Path $env:TEMP 'gpt_rag_ui-3.5.0-py3-none-any.whl'
python -m unittest discover -s tests -p test_presentation_packaging.py -q
git --no-pager diff --check
git -C $ORCH --no-pager diff --check
git -C $UI --no-pager diff --check
git -C 'C:\Users\paulolacerda\.copilot\repos\copilot-worktrees\ai-landing-zones\inline-visual-output' --no-pager diff --check
```

Change-to-test mapping: structural/config/hydration/carrier/deadline/action
cases reside in ORCH runtime/presentation modules; producer merge/checkpoint
cases in its multi-agent module; UI admission/native restore in native handlers,
typed projection/exact sort in inline-presentation helpers, attribution/replay
in multi-agent tests, actual JSX in browser smoke and distribution integrity
in umbrella packaging tests. Three reviewed sales/operations/finance source
domains use the retained `source-fixture.json`. Settings/selection/turn schema
hashes respectively remain `98295024fbe702890f2a69faeb086e6f3e526b73c05257f580914363d0225d82`,
`48f340384553170cfbc87a10ecc1d3c318078541a271a91e97f472dc332e0a04`,
`cdd7543e522417affac96fd90cc602a4b564ead495ae7b02db53d8e17624f07d`.
Receipts cover uncommitted edits over the baselines above, not release images.
Reader-first rollout and disable-production/retain-readers rollback have not
been executed. Full candidate acceptance remains mandatory before opt-in.

## Final focused local hardening receipt

This supersedes earlier component/browser counts, not real-host acceptance.
The ORCH four-module suite including `test_native_presentation_safety.py`
passed **102 tests in 13.62s**. Four subsequent action-hydration cases passed
with the safety module: **21 tests in 2.67s**. Native handlers passed
**11 tests in 2.343s**, reader/helpers **15**, replay **1**. Scoped Ruff passes.
Exact before/at/after deadlines, retries under one budget, Unicode byte limits,
uncooperative cancellation and safe correlated diagnostics are covered locally.
Opaque native citations survive guarding; restored `items` citations are
assistant-admitted, not taken from user/tool/progress imitations.
Optional element-construction failure now retains readable accepted text.
All-null charts/repeated category row IDs are rejected independently.
Business actions require a captured matching string identifier, not `row-N`.

Final Chromium run: **1 passed in 21.939s**, **eleven** payload scenarios in
each of standalone/iframe × light/dark. Long source/card/category labels first
caused page overflow in all four views. Minimal card grid sizing and a local
scrolling exact-value table corrected it; the viewport overflow assertion now
passes. Existing exact/null geometry, status/follow-up filter/copy, keyboard
inspection/activation, spoof/future/malformed/plain fallback and duplicate
activation checks remain passing, with zero external requests/errors.
The final run writes eight screenshots and four trace ZIPs under
`UI/.artifacts/inline-presentation-playwright/`; these synthetic artifacts are
ignored, not product documentation or live acceptance.

Controlled NativeService metadata/state tests deny history/new actions after
ownership-access revocation before native execution. They do not prove real
host deletion, retained-history source revocation or deployed source ACL changes.
Both current wheels were rebuilt with existing backends; exact schema hashes,
LF and package-only imports passed **1 test in 3.991s**. Available UI
setuptools75/Chainlit2.9 evidence is not declared setuptools84/Chainlit2.12
qualification. Two secure TLS failures remain the declared-pin install blocker;
no further installation was attempted or certificate verification weakened.

Additional reproducible commands, with variables/bootstrap defined above:

```powershell
Set-Location $ORCH
$env:PYTHONPATH = "src;$UI\src"
& $NATIVE -m pytest tests/test_native_presentation_safety.py tests/test_native_presentation.py tests/test_native_runtime.py tests/test_native_presentation_multi_agent.py -q --maxfail=1
# 102 passed before the four subsequent action cases; not claimed rerun afterward.
& $NATIVE -m pytest tests/test_native_presentation_safety.py -q --maxfail=1
# 21 passed in final focused run.
python -m ruff check src/native/presentation.py src/native/presentation_middleware.py tests/test_native_presentation_safety.py
Set-Location $UI
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p test_inline_presentation_browser.py -v
# 1 passed in 21.939s; 11 payloads × 4 views, real production JSX.
```

Newly closed local tasks: T008, T012, T018, T028, T029, T032, T035, T036,
T040, T041 and T046. Proposed separate action/safety modules reuse collected
ORCH safety/presentation tests and UI native/inline/browser tests. Full history/
interrupted/deletion/provider/channel inventory and acceptance obligations
remain explicitly unchecked in tasks.md. No live gate is replaced by mocks.

## Unauthenticated Playwright harness

Explicit user authorization permits mocked data/API/auth boundaries only in
the test harness. No production authentication code or setting was weakened.
The harness routes a local mocked API through production `rest_projection`
and `text_projection`, then runs the complete production `Presentation.jsx`
using installed Chainlit's real React runner and Playwright Chromium.
No sign-in, app server, Azure or external resource is required.

From the UI checkout:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p test_inline_presentation_browser.py -v
python -m unittest discover -s tests -p test_inline_presentation.py -q
python -m unittest discover -s tests -p test_inline_presentation_multi_agent.py -q
python -m ruff check tests/test_inline_presentation_browser.py
git --no-pager diff --check
```

Final browser test **passed in 19.650s**; reader/helpers **14 passed**, replay
**1 passed**, scoped Ruff passed. Browser cases run all ten payload scenarios
in each of four standalone/iframe × light/dark combinations:

- Cards/table/chart exact `9.750` and USD labels; null chart/table gaps remain
  `—`, never zero or a plotted measurement.
- Exact sorting/null-last ordering, displayed status filtering, filtered-row
  clipboard including visible status/follow-up headings and preserved scale.
- A sorted/filtered March row sends exactly its saved business-ID prompt.
  Keyboard chart inspection traverses exact/null values; pointer row and
  keyboard suggestion activation each send one normal message, pending
  duplicate activation is suppressed.
- Unknown blocks/props do not propagate; HTML-looking labels remain plain
  text; malformed known tables retain siblings/readable fallback; future
  versions retain text without visuals.
- User/tool/progress, guarded-primary and incomplete imitations produce no
  visual controls. Ordinary text remains readable.
- Zero external requests and zero runner/page errors.

The real-browser test created these ignored synthetic-only artifacts under
`UI\.artifacts\inline-presentation-playwright\`:

| View/theme | Render screenshot | Future-version text screenshot | Trace |
| --- | --- | --- | --- |
| Standalone/light | `standalone-light.png` | `standalone-light-fallback.png` | `standalone-light.zip` |
| Standalone/dark | `standalone-dark.png` | `standalone-dark-fallback.png` | `standalone-dark.zip` |
| Iframe/light | `embed-light.png` | `embed-light-fallback.png` | `embed-light.zip` |
| Iframe/dark | `embed-dark.png` | `embed-dark-fallback.png` | `embed-dark.zip` |

Use the existing Playwright CLI to inspect traces locally:
`python -m playwright show-trace .artifacts/inline-presentation-playwright/standalone-light.zip`.
No browser/tool installation was necessary. The current UI wheel was rebuilt
with the available backend after the visible-status/copy refinement; declared
setuptools 84.1.0 qualification remains blocked. The available backend warns
about the asset-only contracts directory; exact archive/package-only tests
verify that the reviewed files are included despite that warning.

This is a mocked-boundary local browser receipt using installed Chainlit
2.9.4, not declared-pin 2.12.0, authenticated production embedding, real
native-state authorization/finalization, the complete accessibility matrix,
30-device render measurements or real analyst acceptance. The earlier actual
middleware-to-handler and 20-run native multi-agent receipts remain valid
for unchanged orchestrator/reader source. T054-T058 remain pending/blocked.

### Production visual styling correction — 2026-11-08

The screenshot is an **isolated CustomElement harness**, not the complete
Chainlit chat application. It exposes the installed Chainlit JSX runner from
its frontend bundle and executes `public/elements/Presentation.jsx`. API/auth
and message dispatch are mocked; the production REST/text projection is real.
The prior harness loaded bundled Chainlit CSS but omitted `public/custom.css`
and the application's `public/theme.json` variables. The renderer additionally
depended on utility classes absent from the precompiled bundle and drew chart
series using foreground color without visible axes/category labels.

Production styling now lives in `public/custom.css`, already configured by
`.chainlit/config.toml`, scoped under `.inline-presentation`. The renderer uses
these explicit styles, inherits Chainlit theme tokens, and supplies compact SVG
plots with zero baselines, approximate scale ticks, category labels, exact
small-chart value labels, eight theme-aware series colors and legends.
Dense category labels are sampled; full exact labels/values remain in the
keyboard-accessible data table. Null values remain unplotted gaps. Decimal
strings, sort/copy behavior, action deduplication and authorization are unchanged.
Cards, tables, status badges, controls and focus indicators share typography,
spacing and borders. Wide tables/charts scroll locally on small screens.

The harness now loads the **same production CSS and theme variables**, without
component-specific screenshot cosmetics. It checks computed styling, chart
height/color/labels, desktop and 390px document containment, local wide-table
scrolling, and the existing interaction/security scenarios.

Reused the feature checkout's existing `.venv-native\Scripts\python.exe`
with `$env:PYTHONPATH = 'src'`; no installations or sign-in:

- Browser command above: **1 passed in 27.847s**, four standalone/iframe ×
  light/dark combinations, desktop/mobile screenshots, zero external requests,
  zero page/runner errors.
- `test_inline_presentation.py`: **15 passed**.
- `test_inline_presentation_multi_agent.py`: **1 passed**.
- Scoped browser-test Ruff: **passed**.
- `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol
  --no-pager diff --check`: **passed**, preserving incumbent CSS CRLF endings.

Updated screenshots/traces remain in
`UI\.artifacts\inline-presentation-playwright\`. In addition to the desktop
and fallback filenames above, the polished small-screen screenshots are
`standalone-light-mobile.png`, `standalone-dark-mobile.png`,
`embed-light-mobile.png`, and `embed-dark-mobile.png`.
Two completed screenshot batches were used, with a final correction to
CSS-generated sort-arrow encoding. These artifacts show the real production
element and styles, **not authenticated app chrome or secure production
embedding**. Declared Chainlit 2.12.0 qualification and the broader acceptance
gates above remain unverified. No Azure operations, manifests, releases or
production authentication changes were made.

### Actual Chainlit chat follow-up — 2026-11-08

Actual local Chainlit `/` chat validation now supplements the isolated renderer
evidence. Test-only entrypoint, configuration, capture script, detailed
reproduction notes and response evidence are retained in
`UI\.artifacts\actual-chainlit\`. The public asset junction references the
existing feature checkout, without modifying production assets or SDK internals.
The synthetic fixture is projected by the production reader and emitted through
a real `cl.Message` with an inline `cl.CustomElement(name="Presentation")`.

Using the existing `.venv-native\Scripts\python.exe`, the final `capture.py`
execution passed: real chat submission, card, data table, exact chart table and
SVG chart, sort/filter behavior, both theme classes, and zero browser page or
renderer errors. `/`, `/public/custom.css` and the actual
`/public/elements/Presentation.jsx` returned HTTP 200. Screenshots:

- `UI\.artifacts\actual-chainlit\chat-light-desktop.png`
- `UI\.artifacts\actual-chainlit\chat-dark-desktop.png`

These are real anonymous Chainlit chat screenshots at 1440 × 1500, not the
isolated renderer. Installed Chainlit is **2.9.4**, versus declared **2.12.0**.
Google Fonts and KaTeX CDN requests were blocked, not fetched. The missing
release metadata footer is expected in the test server. The presentation
continues beneath the fixed composer in the chat scroller. Anonymous mode has
no persisted history sidebar; authenticated sidebar, production identity,
backend admission, secure embedding/mobile and pinned-version validation are
not established by these shots. No production root-cause fix was required.

The loopback server was stopped and no listener remained on port 8765.
Existing dirty feature files were preserved. No issue #691 posting, upload,
commit, push, release, deployment or Azure command was performed. Preview and
explicit human approval remain required before any GitHub posting.

## Local US4 history receipt — 2026-11-08

**T042, T043 and T047 are complete for their local criteria only. Live gates
remain false: T054/T057 native-host reads and human acceptance are NOT RUN.**
This receipt was inserted after confirmation that no concurrent shared
tasks/quickstart edits remained. No fixture count below is a real conversation
or final human acceptance count.

### Delivered behavior and changed files

- ORCH `tests/test_native_presentation_history.py`: public agent response
  roundtrip; approve/reject workflow checkpoint resume; readable review;
  optional presentation omission/preservation; unchanged source/selection
  counts on recorded research resume; cancelled agent/workflow runs do not
  return completed output.
- UI `tests/test_native_presentation_history.py`: fresh official OpenAI SDK
  response/input reads through controlled HTTP transport and fresh Durable
  SDK state/workflow reads through controlled `TaskHubGrpcClient` boundaries.
  Covers completed/interrupted/legacy/future-block and workflow results,
  saved citations, owner denial, missing native state, metadata admission
  revocation, and retained saved snapshots despite denial of new source work.
- UI `src/gpt_rag_ui/services/native_presentation.py`: a failing regression
  exposed completed Hosted workflow business JSON inside assistant messages
  not projecting visually. The reader now decodes one complete, bounded,
  typed completed result, retaining readable review and native message
  identity/deduplication. It does not search substrings in flattened narration;
  user/tool carriers remain visually inert.

No storage, history API, settings/provider, deployment, authentication,
contract-version or manifest change. Existing native serializers and
owner-admitted history paths remain authoritative. The UI reader consumes
the existing ORCH optional business envelope. Central unshipped documentation
coordination remains separate; this receipt does not claim published product
documentation or live acceptance is complete.

### Actual commands and results

Use `$ORCH`, `$UI`, `$NATIVE` from “Reproducible latest local commands” above.
No dependencies were installed for these runs.

```powershell
Set-Location $ORCH
$env:PYTHONPATH = 'src;tests'
& $NATIVE -m pytest tests/test_native_presentation_history.py -q --maxfail=1
# 7 passed in 4.93s.
& $NATIVE -m pytest tests/test_native_presentation_history.py tests/test_native_presentation_multi_agent.py -q --maxfail=1
# 29 passed in 15.58s, including existing multi-agent checkpoint regressions.
python -m ruff check tests/test_native_presentation_history.py
git --no-pager diff --check -- tests/test_native_presentation_history.py
# Both passed.
```

UI compatible-package bootstrap, retaining installed Chainlit:

```powershell
Set-Location $UI
$env:PYTHONPATH = "src;$ORCH\src;$ORCH\tests"
$env:INLINE_ORCH_TESTS = '1'
@'
import sys, unittest
import chainlit
p = r'C:/Users/paulolacerda/.copilot/session-state/476dbbfa-6c86-4114-b531-3e685ea23877/files/native-maf-smoke/.venv-published/Lib/site-packages'
sys.path.insert(0,p)
import agent_framework, agent_framework.openai, agent_framework_foundry, durabletask.client
sys.path.remove(p)
sys.path.append(p)
sys.path.insert(0,'tests')
from test_native_presentation_history import NativeHistoryTests
from test_native_presentation import NativePresentationTests
suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeHistoryTests)
for name in ('test_history_citations_preserved_only_in_admitted_assistant_messages', 'test_local_history_revocation_and_new_action_fail_before_native_access', 'test_optional_business_fields_omit_nonvisual_and_keep_saved_values', 'test_actual_middleware_handler_disabled_deadline_spoof_and_native_restore'):
    suite.addTest(NativePresentationTests(name))
r=unittest.TextTestRunner().run(suite)
sys.exit(not r.wasSuccessful())
'@ | python -
# 8 passed in 6.181s; cross-component integration executed, not skipped.
python -m unittest discover -s tests -p test_inline_presentation.py -q
# 17 passed in 0.388s.
python -m ruff check src/gpt_rag_ui/services/native_presentation.py tests/test_native_presentation_history.py
git --no-pager diff --check -- src/gpt_rag_ui/services/native_presentation.py tests/test_native_presentation_history.py
# Both passed.
```

After the final Hosted interrupted-output fixture addition, the exact final
history-only command was:

```powershell
Set-Location $UI
$env:PYTHONPATH = 'src'
@'
import sys, unittest
import chainlit
p = r'C:/Users/paulolacerda/.copilot/session-state/476dbbfa-6c86-4114-b531-3e685ea23877/files/native-maf-smoke/.venv-published/Lib/site-packages'
sys.path.insert(0,p)
import agent_framework, agent_framework.openai, agent_framework_foundry, durabletask.client
sys.path.remove(p)
sys.path.append(p)
sys.path.insert(0,'tests')
from test_native_presentation_history import NativeHistoryTests
r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeHistoryTests))
sys.exit(not r.wasSuccessful())
'@ | python -
# 4 passed in 3.159s.
python -m ruff check src/gpt_rag_ui/services/native_presentation.py tests/test_native_presentation_history.py
git --no-pager diff --check -- src/gpt_rag_ui/services/native_presentation.py tests/test_native_presentation_history.py
# Both passed.
```

Initial failures exposed an incorrect test response type, assistant-only
readable projection expectations, and the genuine Hosted business projection
gap. These were resolved; initial failed runs are not passing evidence.

### Historical retired actual-Azure matrix — 20 cases, all NOT RUN

This former Azure matrix is retired by the 2026-11-08 scope amendment, not
pending or scheduled. It is retained only as historical evidence. T057's active
20-case matrix uses distinct local controlled SDK/history cases instead.

Each ID below denotes one distinct real native conversation/process. Repeated
reads of one ID, local fixtures and browser samples never count as additional
real conversations. The paired columns enumerate ten Hosted and ten Durable
cases, not twenty executed cases.

| Hosted ID/status | Durable ID/status | Scenario |
| --- | --- | --- |
| H01 — NOT RUN | D01 — NOT RUN | Legacy text-only completed conversation |
| H02 — NOT RUN | D02 — NOT RUN | Single-agent completed visual answer |
| H03 — NOT RUN | D03 — NOT RUN | Multi-agent completed visual answer |
| H04 — NOT RUN | D04 — NOT RUN | Interrupted agent turn |
| H05 — NOT RUN | D05 — NOT RUN | Workflow waiting for readable human review |
| H06 — NOT RUN | D06 — NOT RUN | Approved completed workflow |
| H07 — NOT RUN | D07 — NOT RUN | Rejected completed workflow |
| H08 — NOT RUN | D08 — NOT RUN | Disable presentation production after saved completion; restore unchanged |
| H09 — NOT RUN | D09 — NOT RUN | Revoke source access, retain conversation access: restore saved snapshot and deny new action |
| H10 — NOT RUN | D10 — NOT RUN | Delete/revoke conversation access: deny text, visuals and new action |

For every ID, record native conversation/process and turn identities, fresh
client read, expected versus actual values/order/citations, and results in
standalone/embedded × light/dark. For completed outcomes, verify reopening
causes zero additional generation, selection or source retrieval. H09/D09
must distinguish conversation admission from source authorization and verify
no independent visual-history source ACL lookup. H10/D10 must include another
owner's denial and subsequent deletion/access revocation without modifying
native history for compatibility.

**Residual gates**: actual Hosted/Durable persistence/restoration, operational
source revocation/deletion, four-view human evidence and final counts await
T054/T057 approval. Local serialization/checkpoint/controlled-boundary
evidence is not proof of deployed persistence or live ACL behavior. No Azure
command/query, demo, login/auth removal, GitHub write, commit, push or release
was performed for this history increment. The whole issue remains incomplete.

### Receipt finalization and whitespace-only follow-up

After concurrent shared evidence edits ended, T042/T043/T047 were marked
complete for the local criteria above. UI `public/custom.css` had CR-at-EOL
warnings on added presentation lines 99–199. Only those added lines were
normalized to LF; byte assertions verified that all styling text, the first
98 existing lines and the final existing closing brace remained unchanged.
No rendering behavior changed and no unrelated tests were rerun.

Validation: `git --no-pager diff --check` in the umbrella and
`git -C $UI --no-pager diff --check` both passed for the full dirty trees.
The prepared real-host matrix remains entirely NOT RUN; no live gate was
opened by marking these local tasks.
