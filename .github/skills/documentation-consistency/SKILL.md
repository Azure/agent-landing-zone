---
name: documentation-consistency
description: Keeps Agent Landing Zone user and operator documentation aligned with shipped behavior. Use for features, configuration keys, deployment parameters, defaults, component pins, operations, or breaking changes.
---

# Agent Landing Zone documentation consistency

User-facing documentation lives on `main` in `Azure/AI-Landing-Zones` and is
published at https://azure.github.io/AI-Landing-Zones/agent-landing-zone/
(ADR-0014). Current product pages describe the latest shipped behavior;
do not add release-comparison blocks or version-gating sidebars.

1. Identify the user or operator behavior that changed.
2. Search the documentation source for the feature, configuration key,
   parameter, component, and previous terminology.
3. Update every affected page in the same coordinated change.
4. Register new pages in `mkdocs.yml`.
5. Keep repository and service READMEs concise; link to the published site
   instead of duplicating product guidance.
6. Ensure examples match current defaults, supported deployment modes, and
   shipped component versions.
7. Report the documentation branch or pull request in the implementation
   handoff.

A user-visible change is incomplete until documentation is updated or the
search demonstrates that no published page is affected.
