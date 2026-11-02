"""Shared, Azure-read-free native application selection for lifecycle hooks."""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Mapping

from config.deployment.composition import (
    describe_application, materialized_settings, validate_hosted_prerequisites,
)
from config.deployment.native import NativeApplication, OrchestrationHost, resolve_application
from config.retrieval.settings import public_settings


def resolve_environment_plan(environment: Mapping[str, str]) -> NativeApplication:
    """Explicit current-product intent only; no persisted-state classification."""
    app = resolve_application(environment)
    public_settings(environment, hosted=app.host is OrchestrationHost.HOSTED)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true", help="Describe the canonical host/mode and component selection as JSON, without Azure lookups.")
    parser.add_argument("--validate-hosted-deploy", action="store_true", help="Validate provisioned Hosted prerequisites and an immutable image.")
    parser.add_argument("--validate-hosted-context", action="store_true", help="Validate provisioned Hosted prerequisites before image preparation.")
    args = parser.parse_args()
    try:
        app = resolve_environment_plan(os.environ)
        if args.validate_hosted_deploy or args.validate_hosted_context:
            if app.host is OrchestrationHost.HOSTED:
                validate_hosted_prerequisites(
                    os.environ, require_image_digest=not args.validate_hosted_context,
                    require_foundry_project=True,
                )
        if args.describe or args.validate_hosted_deploy or args.validate_hosted_context:
            print(json.dumps(describe_application(os.environ)))
        else:
            for key, value in materialized_settings(os.environ).items():
                print(f"{key}={value}")
    except ValueError as error:
        logging.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
