"""Provider-neutral application resolution on plain camelCase input values.

This boundary deliberately does not resolve Azure identities, resource names,
bindings or deployment-time expressions. Existing lifecycle modules own those
operations. Bicep keeps its azd substitution/rendering contract.
"""

from __future__ import annotations

import copy
from typing import Mapping

from config.deployment.composition import _resolve_application_overrides
from config.deployment.existing_images import apply_existing_images
from config.deployment.firewall import resolve_firewall_inputs


def resolve_parameters(
    source: Mapping[str, object],
    environment: Mapping[str, str],
    *,
    expected_hosted_source_commit: str | None = None,
    existing_images: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return independent plain values with the existing application decisions.

    Supplied settings are data: adapters resolve their placeholders once before
    this boundary, so literal replacement strings are never reinterpreted.
    """
    result = copy.deepcopy(dict(source))
    result.update(_resolve_application_overrides(
        result, environment,
        expected_hosted_source_commit=expected_hosted_source_commit,
    ))
    result.update(resolve_firewall_inputs(source, environment))
    if existing_images:
        apply_existing_images(result["containerAppsList"], existing_images)
    return result
