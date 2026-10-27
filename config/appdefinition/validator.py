"""Schema and semantic validation of application definitions (FR-015d/e, R10).

Validation is pure: it reads only the definition, its folder, and
``manifest.json``. It never contacts Azure, so it can run in ``preprovision``
before any resource changes. Every issue carries a JSON pointer.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from config import find_repo_root

from .errors import AppDefinitionValidationError, ValidationIssue
from .loader import KIND_CONTAINER_APP, KIND_HOSTED_AGENT, AppDefinition
from .profiles import PROFILES

if TYPE_CHECKING:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError

SCHEMA_RELATIVE_PATH = Path("contracts") / "app-definition-v1.schema.json"
RESERVED_SETTING_PREFIX = "AGENTLZ_"
AZURE_YAML = "azure.yaml"
UNPINNED_SOURCE_MESSAGE = "source must be a 40-character commit or a sha256 image digest."

#: Bundled component name -> manifest component name suffix. Suffix matching
#: keeps the pin check valid across the component repository renames.
BUNDLED_MANIFEST_SUFFIX = {
    "ui": "-ui",
    "orchestrator": "-orchestrator",
    "ingestion": "-ingestion",
}

_HOST_FOR_KIND = {
    KIND_CONTAINER_APP: "containerapp",
    KIND_HOSTED_AGENT: "azure.ai.agent",
}


def _escape(token: object) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer(*tokens: object) -> str:
    """Build an RFC 6901 JSON pointer from path tokens."""
    return "".join(f"/{_escape(token)}" for token in tokens)


@lru_cache(maxsize=4)
def _validator(schema_path: str) -> Draft202012Validator:
    from jsonschema import Draft202012Validator

    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_path(repo_root: Path | None = None) -> Path:
    return (repo_root or find_repo_root()) / SCHEMA_RELATIVE_PATH


def _schema_issue(error: ValidationError, document: Any) -> Iterator[ValidationIssue]:
    location = list(error.absolute_path)
    where = pointer(*location)
    keyword = error.validator
    instance = error.instance

    if keyword == "additionalProperties" and isinstance(instance, dict):
        allowed = set(error.schema.get("properties", {}))
        for name in sorted(set(instance) - allowed):
            reason = (
                "lifecycle hooks are not allowed in an application definition."
                if name == "hooks"
                else f"property `{name}` is not allowed."
            )
            yield ValidationIssue(pointer(*location, name), reason)
        return
    if location and location[-1] == "source" or (
        len(location) >= 2 and location[-2] == "source"
    ):
        source_pointer = pointer(*location[: location.index("source") + 1])
        yield ValidationIssue(source_pointer, UNPINNED_SOURCE_MESSAGE)
        return
    if len(location) >= 2 and location[-2] == "profiles" and keyword == "enum":
        yield ValidationIssue(
            where,
            f"profile `{instance}` is not supported. Supported: "
            + ", ".join(PROFILES)
            + " (base is implicit and must not be listed).",
        )
        return
    if (
        location
        and location[-1] == "key"
        and isinstance(instance, str)
        and instance.startswith(RESERVED_SETTING_PREFIX)
    ):
        yield ValidationIssue(
            where, f"keys starting with `{RESERVED_SETTING_PREFIX}` are reserved."
        )
        return
    if location == ["components"] and keyword == "minItems":
        yield ValidationIssue(where, "at least one component is required.")
        return
    if keyword == "required" and isinstance(instance, dict):
        for name in error.validator_value:
            if name not in instance:
                yield ValidationIssue(pointer(*location, name), "is required.")
        return
    if keyword == "not" and isinstance(instance, dict) and "kind" in instance:
        for name in ("ingress", "resources"):
            if name in instance:
                yield ValidationIssue(
                    pointer(*location, name),
                    f"`{name}` is not allowed for `azure.ai.agent` components.",
                )
        return
    if keyword == "not" and isinstance(instance, dict):
        yield ValidationIssue(where, "`value` and `secret` are mutually exclusive.")
        return
    yield ValidationIssue(where, error.message)


def _schema_issues(document: Any, repo_root: Path | None) -> list[ValidationIssue]:
    validator = _validator(str(schema_path(repo_root)))
    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(map(str, e.absolute_path))):
        for issue in _schema_issue(error, document):
            if issue not in issues:
                issues.append(issue)
    return issues


def _walk_strings(value: Any, location: tuple[object, ...] = ()) -> Iterator[tuple[tuple[object, ...], str]]:
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, (*location, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, (*location, index))


def _semantic_issues(definition: AppDefinition, repo_root: Path | None) -> list[ValidationIssue]:
    document = definition.document
    issues: list[ValidationIssue] = []

    for location, text in _walk_strings(document):
        if location and location[0] == "$schema":
            continue
        if "://" in text:
            issues.append(
                ValidationIssue(pointer(*location), "remote URLs are not allowed; use a local path and a pinned source.")
            )

    components = [c for c in document.get("components") or [] if isinstance(c, dict)]
    seen_names: dict[str, int] = {}
    for index, component in enumerate(components):
        name = component.get("name")
        if isinstance(name, str):
            if name in seen_names:
                issues.append(ValidationIssue(pointer("components", index, "name"), f"component name `{name}` is already used by /components/{seen_names[name]}."))
            else:
                seen_names[name] = index

    app_keys: dict[str, str] = {}
    for index, setting in enumerate(document.get("settings") or []):
        key = setting.get("key") if isinstance(setting, dict) else None
        if isinstance(key, str):
            if key in app_keys:
                issues.append(ValidationIssue(pointer("settings", index, "key"), f"setting `{key}` is already declared at {app_keys[key]}."))
            else:
                app_keys[key] = pointer("settings", index, "key")
    for c_index, component in enumerate(components):
        local: dict[str, str] = {}
        for s_index, setting in enumerate(component.get("settings") or []):
            key = setting.get("key") if isinstance(setting, dict) else None
            if not isinstance(key, str):
                continue
            where = pointer("components", c_index, "settings", s_index, "key")
            previous = local.get(key) or app_keys.get(key)
            if previous:
                issues.append(ValidationIssue(where, f"setting `{key}` is already declared at {previous}."))
            else:
                local[key] = where

    if definition.bundled:
        issues.extend(_bundled_pin_issues(components, repo_root))
    else:
        issues.extend(_folder_issues(definition, components))
    return issues


def _bundled_pin_issues(components: list[dict[str, Any]], repo_root: Path | None) -> list[ValidationIssue]:
    """The bundled trio's sources must equal the release manifest pins."""
    root = repo_root or find_repo_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    pins = {
        entry.get("name", ""): entry.get("commit", "")
        for entry in manifest.get("components", [])
        if isinstance(entry, dict)
    }
    issues: list[ValidationIssue] = []
    for index, component in enumerate(components):
        suffix = BUNDLED_MANIFEST_SUFFIX.get(component.get("name", ""))
        if suffix is None:
            issues.append(ValidationIssue(pointer("components", index, "name"), "the bundled definition only declares ui, orchestrator, and ingestion."))
            continue
        matches = [commit for name, commit in pins.items() if name.endswith(suffix)]
        source = component.get("source") or {}
        if len(matches) != 1:
            issues.append(ValidationIssue(pointer("components", index, "source"), f"manifest.json must pin exactly one component ending in `{suffix}`."))
        elif source.get("commit") != matches[0]:
            issues.append(ValidationIssue(pointer("components", index, "source", "commit"), f"must equal the manifest.json pin `{matches[0]}`."))
    return issues


def _folder_issues(definition: AppDefinition, components: list[dict[str, Any]]) -> list[ValidationIssue]:
    import yaml

    folder = definition.folder.resolve()
    azure_yaml = folder / AZURE_YAML
    issues: list[ValidationIssue] = []
    for index, component in enumerate(components):
        relative = component.get("path")
        if not isinstance(relative, str):
            continue
        target = (folder / relative).resolve()
        if not target.is_relative_to(folder):
            issues.append(ValidationIssue(pointer("components", index, "path"), "must stay inside the application folder."))
        elif not target.exists():
            issues.append(ValidationIssue(pointer("components", index, "path"), f"`{relative}` does not exist in {folder}."))

    if not azure_yaml.is_file():
        issues.append(ValidationIssue("", f"The app folder `{folder}` must contain its own {AZURE_YAML}."))
        return issues
    try:
        project = yaml.safe_load(azure_yaml.read_text(encoding="utf-8-sig")) or {}
    except yaml.YAMLError as error:
        issues.append(ValidationIssue("", f"{azure_yaml} is not valid YAML: {error}"))
        return issues
    if not isinstance(project, dict):
        issues.append(ValidationIssue("", f"{azure_yaml} must be a YAML mapping."))
        return issues
    if "hooks" in project:
        issues.append(ValidationIssue("", f"{AZURE_YAML}#/hooks: lifecycle hooks are not allowed in a custom application."))
    services = project.get("services") or {}
    if not isinstance(services, dict):
        services = {}
    for service_name, service in services.items():
        if isinstance(service, dict) and "hooks" in service:
            issues.append(ValidationIssue("", f"{AZURE_YAML}#{pointer('services', service_name, 'hooks')}: lifecycle hooks are not allowed in a custom application."))
    for index, component in enumerate(components):
        name = component.get("name")
        if not isinstance(name, str):
            continue
        service = services.get(name)
        if not isinstance(service, dict):
            issues.append(ValidationIssue(pointer("components", index, "name"), f"{AZURE_YAML} has no service named `{name}`."))
            continue
        expected_host = _HOST_FOR_KIND.get(component.get("kind", ""))
        if expected_host and service.get("host") != expected_host:
            issues.append(ValidationIssue(pointer("components", index, "kind"), f"{AZURE_YAML} service `{name}` must use `host: {expected_host}`."))
    return issues


def collect_issues(definition: AppDefinition, repo_root: Path | None = None) -> list[ValidationIssue]:
    """Return every schema issue, or every semantic issue when the schema passes."""
    issues = _schema_issues(definition.document, repo_root)
    if issues:
        return issues
    return _semantic_issues(definition, repo_root)


def validate_definition(definition: AppDefinition, repo_root: Path | None = None) -> AppDefinition:
    """Raise :class:`AppDefinitionValidationError` when ``definition`` is invalid."""
    issues = collect_issues(definition, repo_root)
    if issues:
        raise AppDefinitionValidationError(str(definition.path), issues)
    return definition
