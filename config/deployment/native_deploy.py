"""Shared native application lifecycle for PowerShell and shell.

Provisioned outputs are authoritative. This module publishes applications and
scoped instance grants, never foundation resources or an execution protocol.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from typing import Callable, Mapping

import yaml

from config import find_repo_root
from config.deployment.composition import hosted_startup_command, hosted_startup_command_sha256, validate_hosted_prerequisites
from config.deployment.hosted import responses_base_url
from config.deployment.hosted_access import apply, discover
from config.deployment.hosted_prepare import prepare_environment
from config.deployment.native import resolve_application, scheduler_settings
from config.deployment.native_access import grant_container_features, grant_runtime_features
from config.deployment.private_network import check_stage
from config.deployment.resource_groups import resource_group_for
from util.azure_cli import resolve_az_command

LOGGER = logging.getLogger(__name__)
Run = Callable[..., subprocess.CompletedProcess]


def required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value or "\0" in value:
        raise ValueError(f"Native deployment requires {name}.")
    return value


def validate_component_source(path: Path, component: str, environment: Mapping[str, str]) -> None:
    if component.endswith("-orchestrator") and resolve_application(environment).host == "container_apps":
        entrypoint = path / "src/native/durable.py"
    elif component.endswith("-ui"):
        entrypoint = path / "src/gpt_rag_ui/config/native.py"
    else:
        return
    if not entrypoint.is_file():
        raise ValueError("Manifest-pinned component lacks its native entrypoint. Coordinate compatible component pins before application activation.")


def runtime_settings(environment: Mapping[str, str]) -> dict[str, str]:
    """Structural settings; functional tool/source configuration stays dynamic."""
    from config.deployment.composition import is_bundled_application

    app = resolve_application(environment)
    settings = app.settings()
    if not is_bundled_application(environment):
        return settings
    if app.host == "container_apps":
        settings.update({"HOSTED_AGENT_BASE_URL": "", "HOSTED_WORKFLOW_BASE_URL": ""})
        settings.update(scheduler_settings(environment))
        for mode, key in (
            ("conversational", "DURABLE_AGENT_NAME"),
            ("workflow", "DURABLE_WORKFLOW_NAME"),
        ):
            if mode in app.publications:
                default = "agent-lz-conversation" if mode == "conversational" else "agent-lz-research-review"
                name = environment.get(key, default)
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
                    raise ValueError(f"{key} must be a stable registration name.")
                if name != default:
                    raise ValueError(f"{key} must match the current published runtime registration: {default}.")
                settings[key] = name
    else:
        settings["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"] = ""
    return settings


def publication_environment(environment: Mapping[str, str], mode: str) -> dict[str, str]:
    values = {**environment, "APPLICATION_MODE": mode, "ORCHESTRATION_HOST": "hosted"}
    if mode == "workflow":
        # Uploads are a conversational frontend capability. Keep the shared
        # 'both' selection intact, but resolve this publication without uploads.
        values["ENABLE_PRIVATE_ATTACHMENTS"] = "false"
        for suffix in ("NAME", "IMAGE", "IMAGE_VERSION", "STARTUP_COMMAND",
                       "IMAGE_SOURCE_COMMIT", "IMAGE_STARTUP_COMMAND_SHA256"):
            target = "HOSTED_AGENT_" + suffix
            source = "HOSTED_WORKFLOW_" + suffix
            if source in environment:
                values[target] = environment[source]
        values["HOSTED_AGENT_NAME"] = environment.get("HOSTED_WORKFLOW_NAME") or (
            environment.get("HOSTED_AGENT_NAME", "agent-app-orchestrator") + "-workflow"
        )
    values.setdefault("HOSTED_AGENT_NAME", "agent-app-orchestrator")
    if values.get("HOSTED_AGENT_DEPLOYMENT"):
        handoff = json.loads(values["HOSTED_AGENT_DEPLOYMENT"])
        handoff["agent"] = {**(handoff.get("agent") or {}), "name": values["HOSTED_AGENT_NAME"]}
        values["HOSTED_AGENT_DEPLOYMENT"] = json.dumps(handoff)
    return values


def render_publication(root: Path, environment: Mapping[str, str], digest: str) -> dict:
    document = yaml.safe_load(
        (root / "config/deployment/templates/native-hosted.yaml").read_text(encoding="utf-8")
    )
    document = copy.deepcopy(document)
    service = document["services"]["publication"]
    service["name"] = required(environment, "HOSTED_AGENT_NAME")
    service["image"] = (
        required(environment, "AZURE_CONTAINER_REGISTRY_ENDPOINT").rstrip("/")
        + "/" + environment.get("HOSTED_AGENT_IMAGE", "agent-app-orchestrator") + "@" + digest
    )
    command = environment.get("HOSTED_AGENT_STARTUP_COMMAND", "").strip()
    command = command or hosted_startup_command(environment)
    if command:
        service["startupCommand"] = command
    service["container"]["resources"] = {
        "cpu": environment.get("HOSTED_AGENT_CONTAINER_CPU", "2"),
        "memory": environment.get("HOSTED_AGENT_CONTAINER_MEMORY", "4Gi"),
    }
    # Each publication must keep its structural mode even when shared AppConfig
    # advertises both. No runtime repairs or legacy store=false adapter.
    service["env"].update({
        "APPLICATION_MODE": environment["APPLICATION_MODE"],
        "ORCHESTRATION_HOST": "hosted",
    })
    return document


def _run(arguments: list[str], *, cwd: Path, run: Run) -> subprocess.CompletedProcess:
    result = run(arguments, cwd=cwd, capture_output=True, text=True, check=False, timeout=1800)
    if result.returncode:
        # Never echo CLI input/output; settings can include reference metadata.
        raise RuntimeError("Native application lifecycle command failed; inspect local CLI diagnostics securely.")
    return result


def _persist(root: Path, environment: Mapping[str, str], settings: Mapping[str, str], run: Run) -> None:
    name = required(environment, "AZURE_ENV_NAME")
    for key, value in settings.items():
        _run(["azd", "env", "set", key, value, "--environment", name, "--no-prompt"], cwd=root, run=run)


def deploy_hosted(root: Path, environment: Mapping[str, str], *, run: Run = subprocess.run) -> dict[str, str]:
    app = resolve_application(environment)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    endpoints = {"HOSTED_AGENT_BASE_URL": "", "HOSTED_WORKFLOW_BASE_URL": ""}
    for mode in app.publications:
        values = publication_environment(environment, mode)
        values.setdefault("HOSTED_AGENT_NAME", "agent-app-orchestrator")
        validate_hosted_prerequisites(values, require_image_digest=False, require_foundry_project=True)
        digest, source_commit = prepare_environment(values, manifest)
        if not digest:
            raise ValueError("Native publication did not produce an immutable image.")
        with tempfile.TemporaryDirectory(prefix="agentlz-native-publication-") as directory:
            project = Path(directory)
            name = required(values, "AZURE_ENV_NAME")
            source = root / ".azure" / name
            if not source.is_dir():
                raise ValueError("Selected azd environment is missing. Run azd provision first.")
            shutil.copytree(source, project / ".azure" / name)
            (project / "azure.yaml").write_text(yaml.safe_dump(
                render_publication(root, values, digest), sort_keys=False,
            ), encoding="utf-8")
            _persist(project, values, {
                "AZD_AGENT_SKIP_ACR": "true",
                "FOUNDRY_PROJECT_ENDPOINT": required(values, "AZURE_AI_PROJECT_ENDPOINT"),
                "AZURE_AI_PROJECT_ID": required(values, "AZURE_AI_PROJECT_RESOURCE_ID"),
            }, run)
            _run(["azd", "deploy", "publication", "--environment", name, "--no-prompt"], cwd=project, run=run)
            # Publication creates the instance identity. Reuse the verified,
            # exact scope bootstrap before exposing endpoints to UI consumers.
            plan = discover(values)
            apply(plan)
            grant_runtime_features(values, plan.principal_id)
            result = _run(["azd", "env", "get-values", "--environment", name, "--output", "json"], cwd=project, run=run)
            output = json.loads(result.stdout)
            endpoint = output.get("AGENT_PUBLICATION_RESPONSES_ENDPOINT", "")
            key = "HOSTED_AGENT_BASE_URL" if mode == "conversational" else "HOSTED_WORKFLOW_BASE_URL"
            endpoints[key] = responses_base_url(endpoint)
        prefix = "HOSTED_AGENT_" if mode == "conversational" else "HOSTED_WORKFLOW_"
        _persist(root, environment, {
            prefix + "NAME": values["HOSTED_AGENT_NAME"],
            prefix + "IMAGE_VERSION": digest,
            prefix + "IMAGE_SOURCE_COMMIT": source_commit or "",
            prefix + "IMAGE_STARTUP_COMMAND_SHA256": hosted_startup_command_sha256(values) if source_commit else "",
        }, run)
    # Do not advertise a partially published 'both' application.
    _persist(root, environment, {**runtime_settings(environment), **endpoints}, run)
    return endpoints


def prepare_container_apps(root: Path, environment: Mapping[str, str], *, run: Run = subprocess.run) -> dict[str, str]:
    settings = runtime_settings(environment)
    command = shlex.split(environment.get("CONTAINER_APPS_WORKER_STARTUP_COMMAND", "python -m native.durable"))
    if not command or any("uvicorn" in part or "hosted_entrypoint" in part for part in command):
        raise ValueError("Container Apps requires the confirmed standalone Durable Extension worker command.")
    group = resource_group_for(environment, "application")
    subscription = required(environment, "AZURE_SUBSCRIPTION_ID")
    apps = json.loads(environment.get("CONTAINER_APPS", "[]"))
    if not isinstance(apps, list):
        raise ValueError("Verified native Container Apps mapping is required.")
    names = {}
    for service in ("frontend", "orchestrator"):
        selected = [row for row in apps if isinstance(row, dict) and row.get("service_name") == service]
        if len(selected) != 1 or not selected[0].get("name"):
            raise ValueError("Native deployment requires exact verified frontend and orchestrator mappings.")
        names[service] = selected[0]["name"]
    _persist(root, environment, settings, run)
    for service in ("frontend", "orchestrator"):
        args = [
            resolve_az_command(), "containerapp", "show", "--name", names[service],
            "--resource-group", group, "--subscription", subscription,
            "--output", "json",
        ]
        response = json.loads(_run(args, cwd=root, run=run).stdout)
        containers = response["properties"]["template"]["containers"]
        if len(containers) != 1 or containers[0]["name"] != service:
            raise ValueError("Native Container App must have exactly its expected worker/UI container.")
        container = containers[0]
        container["env"] = [
            item for item in container.get("env", []) if item["name"] not in settings
        ] + [{"name": key, "value": value} for key, value in settings.items()]
        if service == "orchestrator":
            container["command"] = command
            container["args"] = []
        with tempfile.TemporaryDirectory(prefix="agentlz-native-container-") as directory:
            path = Path(directory) / "application.yaml"
            path.write_text(yaml.safe_dump(response), encoding="utf-8")
            _run([
                resolve_az_command(), "containerapp", "update", "--name", names[service],
                "--resource-group", group, "--subscription", subscription, "--yaml", str(path),
            ], cwd=root, run=run)
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--validate-component-source", type=Path)
    parser.add_argument("--component")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        root = find_repo_root()
        if args.validate_component_source:
            if not args.component:
                raise ValueError("--component is required for source validation.")
            validate_component_source(args.validate_component_source, args.component, os.environ)
            settings = {}
        elif args.settings:
            from config.deployment.setup_settings import load_setup_environment
            settings = runtime_settings(load_setup_environment(os.environ, project_root=root))
        elif args.deploy:
            from config.deployment.composition import is_bundled_application
            from config.deployment.setup_settings import load_setup_environment
            if not is_bundled_application(os.environ):
                LOGGER.info("Custom definition selected; bundled native publication/worker is not selected.")
                print("{}")
                return 0
            environment = load_setup_environment(os.environ, project_root=root)
            check_stage(environment, "pre-deploy")
            grant_container_features(environment)
            app = resolve_application(environment)
            settings = (
                deploy_hosted(root, environment) if app.host == "hosted"
                else prepare_container_apps(root, environment)
            )
        else:
            raise ValueError("Select --deploy or --settings.")
        print(json.dumps(settings))
    except (OSError, ValueError, RuntimeError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
