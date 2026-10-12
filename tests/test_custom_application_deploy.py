"""Immutable custom deployment and private build regressions."""

import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from config.deployment import custom_application as deploy

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "a" * 64
COMMIT = "1" * 40
ENV = {
    "AZURE_ENV_NAME": "offline",
    "NETWORK_ISOLATION": "true",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT": "private.azurecr.io",
    "AZURE_RESOURCE_GROUP": "offline",
    "ACR_TASK_AGENT_POOL": "build-pool",
}


def test_pinned_digest_replaces_mutable_tag_without_build(tmp_path):
    component = {"source": {"imageDigest": DIGEST}}
    service = {"image": "${REGISTRY}/application:v1"}
    assert deploy.prepare_image(component, service, tmp_path, {"REGISTRY": "private.azurecr.io"}) == (
        f"private.azurecr.io/application@{DIGEST}"
    )
    with pytest.raises(ValueError, match="qualified service image"):
        deploy.prepare_image(component, {}, tmp_path, ENV)
    with pytest.raises(ValueError, match="environment variable"):
        deploy.prepare_image(component, service, tmp_path, {})


def test_private_build_selects_pool_and_pins_management_plane_digest(tmp_path):
    component = {"name": "web", "path": "src", "source": {"commit": COMMIT}}
    service = {"project": "./src", "language": "docker", "docker": {"remoteBuild": True}}
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout=COMMIT)), \
            patch.object(deploy, "check_stage") as network, \
            patch.object(deploy, "validate_acr_agent_pool") as pool, \
            patch.object(deploy, "build_source_image", return_value=DIGEST) as build:
        assert deploy.prepare_image(component, service, tmp_path, ENV) == (
            f"private.azurecr.io/agent-landing-zone/custom/web@{DIGEST}"
        )
    assert pool.call_args.kwargs["agent_pool"] == "build-pool"
    network.assert_called_once_with(ENV, "hosted-build")
    assert build.call_args.kwargs["agent_pool"] == "build-pool"
    assert build.call_args.kwargs["source_dir"] == (tmp_path / "src").resolve()


@pytest.mark.parametrize("change,match", [
    ({"ACR_TASK_AGENT_POOL": ""}, "ACR_TASK_AGENT_POOL"),
    ({"AZURE_CONTAINER_REGISTRY_ENDPOINT": ""}, "registry endpoint"),
])
def test_private_build_rejects_missing_inputs_without_build(tmp_path, change, match):
    component = {"name": "web", "path": "src", "source": {"commit": COMMIT}}
    service = {"project": "./src", "language": "docker"}
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout=COMMIT)), \
            patch.object(deploy, "build_source_image") as build:
        with pytest.raises(ValueError, match=match):
            deploy.prepare_image(component, service, tmp_path, {**ENV, **change})
    build.assert_not_called()


@pytest.mark.parametrize("image", [
    "application:latest", "https://private.azurecr.io/application",
    "private.azurecr.io/application --build-arg=unsafe", "${REGISTRY}/application",
])
def test_digest_pin_rejects_unqualified_or_invalid_images(tmp_path, image):
    with pytest.raises(ValueError):
        deploy.prepare_image({"source": {"imageDigest": DIGEST}}, {"image": image}, tmp_path, {})


def test_public_source_preserves_azd_build_and_still_checks_commit(tmp_path):
    component = {"name": "web", "path": "src", "source": {"commit": COMMIT}}
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout=COMMIT)), \
            patch.object(deploy, "build_source_image") as build:
        assert deploy.prepare_image(component, {"language": "python"}, tmp_path, {}) is None
    build.assert_not_called()
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout="2" * 40)):
        with pytest.raises(ValueError, match="HEAD does not match"):
            deploy.prepare_image(component, {}, tmp_path, {})


@pytest.mark.parametrize("service,match", [
    ({"project": "src", "language": "python"}, "language: docker"),
    ({"project": "another", "language": "docker"}, "project must match"),
    ({"project": "src", "language": "docker", "docker": {"buildArgs": {"X": "value"}}},
     "cannot preserve these docker options"),
    ({"project": "src", "language": "docker", "docker": {"path": "other.Dockerfile"}},
     "require Dockerfile"),
    ({"project": "src", "language": "docker", "docker": {"context": ".."}},
     "require Dockerfile"),
])
def test_private_build_rejects_unsupported_layout_and_options(tmp_path, service, match):
    component = {"name": "web", "path": "src", "source": {"commit": COMMIT}}
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout=COMMIT)), \
            patch.object(deploy, "check_stage") as network, \
            patch.object(deploy, "build_source_image") as build:
        with pytest.raises(ValueError, match=match):
            deploy.prepare_image(component, service, tmp_path, ENV)
    network.assert_not_called()
    build.assert_not_called()


@pytest.mark.parametrize("boundary", ["check_stage", "validate_acr_agent_pool", "build_source_image"])
def test_private_build_propagates_network_pool_and_build_failures(tmp_path, boundary):
    component = {"name": "web", "path": "src", "source": {"commit": COMMIT}}
    service = {"project": "src", "language": "docker"}
    with patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(stdout=COMMIT)), \
            patch.object(deploy, "check_stage"), \
            patch.object(deploy, "validate_acr_agent_pool"), \
            patch.object(deploy, "build_source_image", return_value=DIGEST), \
            patch.object(deploy, boundary, side_effect=RuntimeError("explicit boundary failure")):
        with pytest.raises(RuntimeError, match="explicit boundary failure"):
            deploy.prepare_image(component, service, tmp_path, ENV)


@pytest.mark.parametrize("failure", [False, True])
def test_deployment_consumes_pin_and_restores_original_yaml(tmp_path, failure):
    app = tmp_path / "sample"
    shutil.copytree(ROOT / "samples" / "custom-app" / "containerapp", app)
    definition_path = app / "app-definition.json"
    definition = json.loads(definition_path.read_text())
    definition["components"][0]["source"] = {"imageDigest": DIGEST}
    definition_path.write_text(json.dumps(definition))
    path = app / "azure.yaml"
    project = yaml.safe_load(path.read_text())
    project["services"]["web"]["image"] = "private.azurecr.io/web:mutable"
    path.write_text(yaml.safe_dump(project))
    original = path.read_bytes()

    def run(args, **kwargs):
        registry.assert_called_once_with("web", f"private.azurecr.io/web@{DIGEST}", ENV)
        rendered = yaml.safe_load(path.read_text())
        service = rendered["services"]["web"]
        assert service["image"] == f"private.azurecr.io/web@{DIGEST}"
        assert service["docker"] == {"imagePassthrough": True}
        assert args == ["azd", "deploy", "web", "--environment", "offline", "--no-prompt"]
        assert kwargs["cwd"] == app
        assert all(kwargs["env"][key] == value for key, value in ENV.items())
        if failure:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    with patch.object(deploy.subprocess, "run", side_effect=run), \
            patch.object(deploy, "configure_service_registry") as registry:
        if failure:
            with pytest.raises(subprocess.CalledProcessError):
                assert deploy.deploy_service(str(definition_path), "web", ENV) == (
                    f"private.azurecr.io/web@{DIGEST}"
                )
        else:
            deploy.deploy_service(str(definition_path), "web", ENV)
    registry.assert_called_once_with("web", f"private.azurecr.io/web@{DIGEST}", ENV)
    assert path.read_bytes() == original


def test_registry_failure_stops_custom_rollout_before_yaml_overlay(tmp_path):
    app = tmp_path / "sample"
    shutil.copytree(ROOT / "samples" / "custom-app" / "containerapp", app)
    path = app / "azure.yaml"
    original = path.read_bytes()
    with patch.object(deploy, "prepare_image", return_value=f"private.azurecr.io/web@{DIGEST}"), \
            patch.object(deploy, "configure_service_registry", side_effect=RuntimeError("registry denied")), \
            patch.object(deploy.subprocess, "run") as run:
        with pytest.raises(RuntimeError, match="registry denied"):
            deploy.deploy_service(str(app / "app-definition.json"), "web", ENV)
    run.assert_not_called()
    assert path.read_bytes() == original


def test_bundled_definition_never_enters_custom_registry_configuration():
    with patch.object(deploy, "configure_service_registry") as registry, \
            patch.object(deploy, "prepare_image") as image:
        with pytest.raises(ValueError, match="bundled component"):
            deploy.deploy_service(str(ROOT / "app-definition.json"), "ui", ENV)
    registry.assert_not_called()
    image.assert_not_called()


@pytest.mark.parametrize("failure", ["none", "deploy", "identity", "roles"])
def test_hosted_deployment_reconciles_only_verified_runtime_profiles(tmp_path, failure):
    app = tmp_path / "hosted"
    shutil.copytree(ROOT / "samples" / "custom-app" / "hosted", app)
    definition_path = app / "app-definition.json"
    definition = json.loads(definition_path.read_text())
    definition["components"][0]["source"] = {"commit": COMMIT}
    definition_path.write_text(json.dumps(definition))
    original = (app / "azure.yaml").read_bytes()
    image = f"private.azurecr.io/agent@{DIGEST}"
    instance = SimpleNamespace(principal_id="verified-principal", agent_version="7")
    with patch.object(deploy, "prepare_image", return_value=image), \
            patch.object(deploy.subprocess, "run") as run, \
            patch.object(deploy, "configure_service_registry") as registry, \
            patch.object(deploy, "discover_instance", return_value=instance) as discover, \
            patch.object(deploy, "assign_hosted_roles") as roles:
        if failure == "deploy":
            run.side_effect = subprocess.CalledProcessError(1, ["azd"])
        if failure == "identity":
            discover.side_effect = RuntimeError("identity mismatch")
        if failure == "roles":
            roles.side_effect = RuntimeError("assignment denied")
        if failure == "none":
            assert deploy.deploy_service(str(definition_path), "agent", ENV) == image
        else:
            with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
                deploy.deploy_service(str(definition_path), "agent", ENV)
        if failure == "deploy":
            discover.assert_not_called()
        else:
            discover.assert_called_once_with(ENV, name="sample-hosted-agent")
        if failure in {"deploy", "identity"}:
            roles.assert_not_called()
        else:
            roles.assert_called_once_with(
                definition["components"][0], instance.principal_id, ENV,
            )
        registry.assert_not_called()
    assert (app / "azure.yaml").read_bytes() == original
