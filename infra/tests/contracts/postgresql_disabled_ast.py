"""Bounded symbolic check, NOT an ARM evaluator or deployed parity evidence.

Only Boolean gates, if, empty arrays and concat are reduced. All other ARM
functions, references, lambda bodies, properties and indices stay opaque AST.
Compare every surviving preexisting field for PG=false in BOTH network modes.
The before input is the exact bounded inverse, whose original field digests
and historical downstream graph fingerprints are checked independently.
"""
import json
import re
import sys

TOKEN = re.compile(r"\s*('(?:[^']|'')*'|-?\d+(?:\.\d+)?|[\w$#-]+|[(),.\[\]])")


def expression(text, isolated):
    tokens = []
    end = 0
    for match in TOKEN.finditer(text):
        assert match.start() == end, f"Unsupported ARM syntax: {text[end:]}"
        tokens.append(match.group(1))
        end = match.end()
    assert end == len(text), f"Unparsed ARM expression: {text[end:]}"
    pos = 0

    def parse():
        nonlocal pos
        token = tokens[pos]
        pos += 1
        if token.startswith("'"):
            result = token[1:-1].replace("''", "'")
        elif re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            result = ("number", token)
        else:
            name = token
            # Namespaced user functions, if present, remain opaque calls.
            while pos + 2 < len(tokens) and tokens[pos] == "." and tokens[pos + 2] == "(":
                name += "." + tokens[pos + 1]
                pos += 2
            assert tokens[pos] == "(", (name, text)
            pos += 1
            args = []
            if tokens[pos] != ")":
                while True:
                    args.append(parse())
                    if tokens[pos] != ",":
                        break
                    pos += 1
            assert tokens[pos] == ")"
            pos += 1
            result = reduce(name, tuple(args))
        while pos < len(tokens) and tokens[pos] in (".", "["):
            if tokens[pos] == ".":
                result = ("property", result, tokens[pos + 1])
                pos += 2
            else:
                pos += 1
                result = ("index", result, parse())
                assert tokens[pos] == "]"
                pos += 1
        return result

    def reduce(name, args):
        if name == "parameters":
            if args == ("deployPostgreSql",):
                return False
            if args == ("networkIsolation",):
                return isolated
        if name == "variables":
            if args == ("_postgreSqlBasic",):
                return False
            if args in (("_acaVnetIntegration",), ("_networkIsolation",)):
                return isolated
        if name in ("true", "false"):
            return name == "true"
        if name == "not" and type(args[0]) is bool:
            return not args[0]
        if name == "if" and type(args[0]) is bool:
            return args[1] if args[0] else args[2]
        if name in ("and", "or"):
            absorbing, identity = (False, True) if name == "and" else (True, False)
            if any(type(a) is bool and a is absorbing for a in args):
                return absorbing
            remaining = tuple(a for a in args if not (type(a) is bool and a is identity))
            if not remaining:
                return identity
            if len(remaining) == 1:
                return remaining[0]
            args = remaining
        if name == "concat":
            args = tuple(a for a in args if a != ("call", "createArray", ()))
            if len(args) == 1:
                return args[0]
        if name == "filter" and args[1][0:2] == ("call", "lambda") and args[1][2][-1] is True:
            return args[0]
        return ("call", name, args)

    result = parse()
    assert pos == len(tokens), f"Trailing tokens: {text}"
    return result


def comparable(value, isolated):
    if isinstance(value, str) and value.startswith("[") and not value.startswith("[["):
        assert value.endswith("]")
        return expression(value[1:-1], isolated)
    if isinstance(value, dict):
        return {k: comparable(v, isolated) for k, v in value.items() if k != "_generator"}
    if isinstance(value, list):
        return [comparable(v, isolated) for v in value]
    return value


def compare(after, before, isolated, path=""):
    if after == before:
        return
    if isinstance(after, dict) and isinstance(before, dict):
        assert set(after) == set(before), f"Membership changed at {path}"
        for key in after:
            if key != "_generator":
                compare(after[key], before[key], isolated, f"{path}/{key}")
    elif isinstance(after, list) and isinstance(before, list):
        assert len(after) == len(before), f"Array membership changed at {path}"
        for i, (a, b) in enumerate(zip(after, before)):
            compare(a, b, isolated, f"{path}/{i}")
    else:
        assert comparable(after, isolated) == comparable(before, isolated), (
            f"Disabled preexisting graph changed (isolated={isolated}): {path}\n"
            f"Actual: {after}\nBefore: {before}"
        )


def check(actual, before):
    assert actual["variables"]["_postgreSqlBasic"] == (
        "[and(parameters('deployPostgreSql'), not(variables('_networkIsolation')))]"
    )
    assert actual["variables"]["_acaVnetIntegration"] == (
        "[or(variables('_networkIsolation'), variables('_postgreSqlBasic'))]"
    )
    assert actual["variables"]["_networkIsolation"] == (
        "[if(empty(string(parameters('networkIsolation'))), false(), bool(parameters('networkIsolation')))]"
    )
    for isolated in (False, True):
        # Drop only new declarations (no deployment side effects), the unused
        # operator-rule loop and a helper-module output. New resource deletion
        # is conditional on its ACTUAL emitted gate evaluating to false.
        current = json.loads(json.dumps(actual))
        for section in ("parameters", "variables"):
            for key in set(current[section]) - set(before[section]):
                del current[section][key]
        assert actual["parameters"]["deployPostgreSql"]["defaultValue"] is False
        for names in ("resourceNames", "_cafResourceNames", "_legacyResourceNames"):
            del current["variables"][names]["postgreSqlServerName"]
        current["variables"]["copy"] = [
            row for row in current["variables"]["copy"] if row["name"] != "_postgreSqlOperatorRules"
        ]
        new_resources = set(current["resources"]) - set(before["resources"])
        assert new_resources == {
            "postgreSql", "postgreSqlValidation", "postgreSqlPrivateEndpoint",
            "containerAppsPostgreSqlNat", "containerAppsPostgreSqlSubnet",
        }
        for name in new_resources:
            condition = current["resources"][name]["condition"]
            assert comparable(condition, isolated) is False, f"{name} deploys with PG disabled"
            del current["resources"][name]
        for resource in current["resources"].values():
            if "dependsOn" in resource:
                resource["dependsOn"] = [d for d in resource["dependsOn"] if d not in new_resources]
        del current["resources"]["natGateway"]["properties"]["template"]["outputs"]["publicIpAddress"]
        # A nonexecuting module's parameter list has no effect; its condition
        # itself must still match. No live module or property is exempted.
        for name in current["resources"]:
            a, b = current["resources"][name], before["resources"][name]
            if "condition" in a and comparable(a["condition"], isolated) is False:
                compare(a["condition"], b["condition"], isolated, f"/resources/{name}/condition")
                current["resources"][name] = b
        compare(current, before, isolated)


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        actual = json.load(f)
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        before = json.load(f)
    check(actual, before)
    # Independent negative evidence: the semantic check, without the digest
    # guard, must reject enabling a new resource or changing a live ACA field.
    for path in (
        ("resources", "postgreSql", "condition"),
        ("resources", "containerEnv", "properties", "parameters", "properties",
         "value", "vnetConfiguration"),
        ("outputs", "VNET_RESOURCE_ID", "value"),
    ):
        changed = json.loads(json.dumps(actual))
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = "[true()]"
        try:
            check(changed, before)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"Disabled AST check swallowed mutation: {path}")
    print("PostgreSQL disabled preexisting graph AST equivalence passed in both network modes; 3 semantic mutations rejected.")
