# Inline presentation customer examples (candidate, not released)

Use the three promoted schema/hash pairs in [`../../`](../../README.md).
These synthetic examples are a local contract, not authorization to opt in a
deployment or a promise that the manifest-pinned release understands it.

| Pair | Valid input | Deliberately invalid input |
| --- | --- | --- |
| Agent settings v1 | `settings-valid.json` | `settings-invalid.json` |
| Presentation selection v1 | `selection-valid.json` | `selection-invalid.json` |
| Completed turn v1 | `presentation-valid.json` | `presentation-invalid.json` |

`source-fixture.json` is the authorized synthetic source for the selection and
completed turn. Shape validation alone does not prove source fidelity or
authorization. Hydration binds values to `sourceId`, `sourceRowId` and field;
the contribution names the source tool and result. March revenue is the decimal
string `9.750` USD, not a binary float rounded to `9.75`. Its `down` indicator
comes from the `revenue-trend` rule against March growth `-2.750`, not model
wording. The all-zero settings revision in this fixture is a synthetic marker,
not a real production revision.

## New text-only adapter

[`text_only_adapter.py`](text_only_adapter.py) imports the matched UI reader;
it deliberately does not duplicate envelope parsing or distribute another
schema. Install the **matched candidate UI wheel** and its declared dependencies
in an isolated environment, or use the checked-out candidate's `src` on
`PYTHONPATH` for local validation. No released version or image is implied.

After your channel's existing authentication, ownership and completed-result
checks, call:

```python
from text_only_adapter import render_text

text = render_text(completed_native_result, owner_admitted=True)
channel.send_text(text)  # Your existing safe text sink, not an HTML/code sink.
```

`completed_native_result` is the host client's original result dictionary,
including assistant/message roles and native IDs, **not** a flattened transcript.
The caller must never let browser input set `owner_admitted`. Keep the original
native result/reference for continuation; this adapter returns only text and
does not mutate native identity, invoke sources, create visual elements or
change authorization.

An admitted future schema version projects only its stable markdown. Unknown
block kinds are inert; known v1 blocks are independently bounded/projected by
the shared reader. Invalid/oversized/unadmitted carriers are not a visual
success. Do not dump raw envelopes as a user-facing fallback, interpret arbitrary
tool/user/progress JSON as presentation, or fetch source data when reopening
saved output. Legacy ordinary text remains ordinary text.

For a contextual follow-up, send an ordinary **new user message** such as
`Compare March with January in USD` using the existing authorized native client
and its current session/reference. Sorting/filtering is local-only; selecting a
suggestion neither calls a business tool directly nor approves a workflow's
pending human review. Text-only users can type the same follow-up.

From the umbrella root, using the candidate UI `src` on `PYTHONPATH`:

```powershell
python -m pytest -q tests/test_presentation_contracts.py tests/test_text_only_adapter.py
```

The central candidate manual is prepared in AI Landing Zones at
`docs/agent-landing-zone/inline-visuals.md` under Agent Application → Chat &
channels → Inline visuals, registered in `mkdocs.yml`.
It is not yet published; service READMEs do not duplicate that manual.
