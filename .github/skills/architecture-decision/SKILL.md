---
name: architecture-decision
description: Conducts and records a verifiable Agent Landing Zone architectural decision. Use when a choice alters repositories, boundaries, contracts, identity, data, deployment topology, or operation with meaningful reversal cost.
---

# Agent Landing Zone architectural decision

1. Load the relevant `engineering-principles` references.
2. Define context, constraints, affected repositories, and up to five
   prioritized characteristics with measures.
3. Compare at least two viable alternatives and the option of not changing.
4. Evaluate identity, authorization, network isolation, component
   compatibility, cost, operation, migration, and reversibility.
5. Record the decision under `docs/adr/` using
   [the ADR template](references/adr-template.md).
6. Define fitness functions, adoption order, rollback or roll-forward, and a
   review trigger.

Do not turn a tool or framework preference into an architectural requirement.
When evidence is missing, record a time-bounded investigation and its decision
criterion instead of guessing.
