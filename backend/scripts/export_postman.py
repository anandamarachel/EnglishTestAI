"""Generate the checked-in Postman collection from docs/api/openapi.json.

Run from any directory. --check verifies that the committed export is current.
The OpenAPI document is the source of truth; no business endpoint is implemented here.
"""

import argparse
import copy
import json
import re
from http import HTTPStatus
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/api/openapi.json"
COLLECTION = ROOT / "docs/api/english-practice.postman_collection.json"
SCHEMA_URL = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
METHODS = {"get", "post", "patch", "put", "delete", "head", "options"}
BODY_VARIABLES = {
    "email": "email",
    "display_name": "display_name",
    "password": "password",
    "current_password": "password",
    "new_password": "new_password",
    "refresh_token": "refresh_token",
    "token": "reset_token",
    "persona_id": "persona_id",
    "topic_id": "topic_id",
    "source_attempt_id": "source_attempt_id",
    "question_id": "question_id",
    "selected_option_id": "option_id",
    "current_question_id": "question_id",
}


def resolve(spec, value):
    if "$ref" not in value:
        return value
    assert value["$ref"].startswith("#/"), "Only local refs are supported by this exporter"
    target = spec
    for part in value["$ref"][2:].split("/"):
        target = target[part.replace("~1", "/").replace("~0", "~")]
    return target


def template_body(value, operation_id):
    if isinstance(value, list):
        return [template_body(item, operation_id) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "revision":
            result[key] = "{{attempt_revision}}"
        elif key == "password_confirmation":
            result[key] = "{{password}}" if operation_id == "register" else "{{new_password}}"
        elif key in BODY_VARIABLES and item is not None:
            result[key] = "{{" + BODY_VARIABLES[key] + "}}"
        else:
            result[key] = template_body(item, operation_id)
    return result


def script_event(kind, lines):
    return {"listen": kind, "script": {"type": "text/javascript", "exec": lines}}


def response_script(operation):
    codes = [int(code) for code in operation["responses"] if code.startswith("2")]
    op = operation["operationId"]
    lines = [
        "// Planned endpoints return 404 until their backend implementation is available.",
        "pm.test('Expected success status', "
        f"() => pm.expect(pm.response.code).to.be.oneOf({codes}));",
        "if (pm.response.code >= 200 && pm.response.code < 300) {",
        "  if (pm.response.code !== 204 && (pm.response.headers.get('Content-Type') || '')"
        ".includes('application/json')) {",
        "    const body = pm.response.json();",
    ]
    if op in ("login", "refreshTokens"):
        lines += [
            "    if (body.access_token) pm.environment.set('access_token', body.access_token);",
            "    if (body.refresh_token) pm.environment.set('refresh_token', body.refresh_token);",
        ]
    # Only copy resources explicitly returned by the operation, never recursively crawl examples.
    lines += [
        "    const attempt = body.attempt || "
        "(body.attempt_id && body.revision !== undefined ? body : null);",
        "    if (attempt) {",
        "      pm.environment.set('attempt_id', attempt.attempt_id);",
        "      pm.environment.set('attempt_revision', String(attempt.revision));",
        "    }",
        "    if (body.attempt_revision !== undefined) "
        "pm.environment.set('attempt_revision', String(body.attempt_revision));",
        "    if (body.exercise_id) pm.environment.set('exercise_id', body.exercise_id);",
        "    const job = body.job || (body.job_id ? body : null);",
        "    if (job) pm.environment.set('job_id', job.job_id);",
        "    if (body.message) pm.environment.set('message_id', body.message.message_id);",
        "    if (body.media_id) pm.environment.set('media_id', body.media_id);",
    ]
    if op == "getExercise":
        lines += [
            "    const question = (body.questions || [])[0];",
            "    if (question) {",
            "      pm.environment.set('question_id', question.question_id);",
            "      const option = (question.options || [])[0];",
            "      if (option) pm.environment.set('option_id', option.option_id);",
            "      else pm.environment.unset('option_id');",
            "    } else { pm.environment.unset('question_id'); "
            "pm.environment.unset('option_id'); }",
            "    if (body.content && body.content.audio) "
            "pm.environment.set('media_id', body.content.audio.media_id);",
        ]
    lines += ["  }"]
    if op in ("logout", "resetPassword", "changePassword"):
        lines += [
            "  pm.environment.unset('access_token');",
            "  pm.environment.unset('refresh_token');",
        ]
    lines += ["}"]
    return lines


def make_item(spec, path, method, operation, example_name=None, example_value=None):
    status = operation["x-implementation-status"]
    name = f"[{status}] {operation['summary']}"
    if example_name and example_name != "default":
        name += f" — {example_name}"
    route = re.sub(r"\{([^}]+)\}", r":\1", path)
    url = {
        "raw": "{{base_url}}" + route,
        "host": ["{{base_url}}"],
        "path": route.strip("/").split("/"),
    }
    headers = [{"key": "Accept", "value": "application/json"}]
    pre = []
    for param_ref in operation.get("parameters", []):
        param = resolve(spec, param_ref)
        key = param["name"]
        if param["in"] == "path":
            url.setdefault("variable", []).append({"key": key, "value": "{{" + key + "}}"})
        elif param["in"] == "query":
            schema = resolve(spec, param["schema"])
            value = str(schema.get("default", schema.get("enum", [""])[0]))
            url.setdefault("query", []).append(
                {
                    "key": key,
                    "value": value,
                    "disabled": key != "limit",
                    "description": param.get("description", "Optional filter"),
                }
            )
        elif key == "Idempotency-Key":
            headers.append({"key": key, "value": "{{request_idempotency_key}}"})
            pre += [
                "// Set idempotency_key in the environment to retry the exact same operation.",
                "const key = pm.environment.get('idempotency_key') || "
                "pm.variables.replaceIn('{{$guid}}');",
                "pm.variables.set('request_idempotency_key', key);",
                "pm.environment.set('last_idempotency_key', key);",
            ]
        elif key == "Range":
            headers.append({"key": key, "value": "bytes=0-1023", "disabled": True})
    active_query = [f"{q['key']}={q['value']}" for q in url.get("query", []) if not q["disabled"]]
    if active_query:
        url["raw"] += "?" + "&".join(active_query)
    request = {
        "method": method.upper(),
        "header": headers,
        "url": url,
        "description": f"Implementation: **{status}**.\n\n{operation['description']}\n\n"
        "See openapi.json for all required fields, constraints and error responses.",
    }
    if operation.get("security") == []:
        request["auth"] = {"type": "noauth"}
    if "requestBody" in operation:
        content = resolve(spec, operation["requestBody"])["content"]
        if "application/json" in content:
            raw = json.dumps(template_body(example_value, operation["operationId"]), indent=2)
            raw = raw.replace('"{{attempt_revision}}"', "{{attempt_revision}}")
            request["body"] = {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}
            headers.append({"key": "Content-Type", "value": "application/json"})
        else:
            # Postman supplies multipart Content-Type with its boundary; never hard-code it.
            request["body"] = {
                "mode": "formdata",
                "formdata": [
                    {
                        "key": "audio",
                        "type": "file",
                        "src": [],
                        "description": "Select your recorded audio file.",
                    },
                    {
                        "key": "client_message_key",
                        "type": "text",
                        "value": "{{request_client_message_key}}",
                    },
                ],
            }
            pre += [
                "const messageKey = pm.environment.get('client_message_key') || "
                "pm.variables.replaceIn('{{$guid}}');",
                "pm.variables.set('request_client_message_key', messageKey);",
                "pm.environment.set('last_client_message_key', messageKey);",
            ]
    if operation["operationId"] == "downloadMedia":
        headers[0]["value"] = "audio/*"
    item = {"name": name, "request": request, "response": [], "event": []}
    if pre:
        item["event"].append(script_event("prerequest", pre))
    item["event"].append(script_event("test", response_script(operation)))
    for code, response_ref in operation["responses"].items():
        response = resolve(spec, response_ref)
        media = response.get("content", {}).get("application/json")
        if media:
            examples = media.get("examples", {"default": {"value": media.get("example")}})
            for label, ex in examples.items():
                item["response"].append(
                    {
                        "name": f"{code} — {label}",
                        "originalRequest": copy.deepcopy(request),
                        "status": HTTPStatus(int(code)).phrase,
                        "code": int(code),
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": json.dumps(ex["value"], indent=2, ensure_ascii=False),
                        "_postman_previewlanguage": "json",
                    }
                )
        elif code == "204":
            item["response"].append(
                {
                    "name": "204 — No Content",
                    "originalRequest": copy.deepcopy(request),
                    "status": "No Content",
                    "code": 204,
                    "header": [],
                    "body": "",
                }
            )
    return item


def build_collection(spec):
    folders = {}
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            folder = folders.setdefault(operation["tags"][0], [])
            media = operation.get("requestBody", {}).get("content", {}).get("application/json")
            examples = media["examples"] if media else {"default": {"value": None}}
            for label, ex in examples.items():
                folder.append(make_item(spec, path, method, operation, label, ex["value"]))
    return {
        "info": {
            "name": "English Practice API — implemented health + planned contract",
            "schema": SCHEMA_URL,
            "description": "Generated from docs/api/openapi.json. "
            "Do not edit this export manually. Only Health is implemented. "
            "Run that folder against the current server; planned requests "
            "will return 404 until implemented. Import the supplied local environment. "
            "Synthetic examples are for review, not proof of live functionality. "
            "A full collection run is not an end-to-end test: "
            "alternatives represent separate flows.",
        },
        "auth": {
            "type": "bearer",
            "bearer": [
                {"key": "token", "value": "{{access_token}}", "type": "string"},
            ],
        },
        "item": [{"name": name, "item": items} for name, items in folders.items()],
    }


def render_collection():
    return (
        json.dumps(build_collection(json.loads(CONTRACT.read_text())), indent=2, ensure_ascii=False)
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if the export needs regeneration"
    )
    args = parser.parse_args()
    output = render_collection()
    if args.check:
        if not COLLECTION.exists() or COLLECTION.read_text() != output:
            raise SystemExit("Postman export is stale. Run: python scripts/export_postman.py")
        print("Postman export is current.")
    else:
        COLLECTION.write_text(output)
        print(f"Wrote {COLLECTION}")


if __name__ == "__main__":
    main()
