"""Validate the planned contract and generated Postman export without a database."""

import copy
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from jsonschema import Draft7Validator, Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from referencing import Registry, Resource

from app.api.router import router
from scripts.export_postman import CONTRACT, METHODS, render_collection, resolve

API_DIR = CONTRACT.parent
SPEC = json.loads(CONTRACT.read_text())
SCHEMAS = SPEC["components"]["schemas"]
RESOURCE = Resource.from_contents(
    {"$schema": "https://json-schema.org/draft/2020-12/schema", **SPEC}
)
REGISTRY = Registry().with_resource("urn:english-contract", RESOURCE)


def validator(schema):
    # Keep local $refs rooted at the complete OpenAPI document.
    resource = {"$schema": "https://json-schema.org/draft/2020-12/schema", **SPEC, **schema}
    return Draft202012Validator(resource, registry=REGISTRY, format_checker=FormatChecker())


def schema_validator(name):
    return validator({"$ref": f"urn:english-contract#/components/schemas/{name}"})


def operations():
    for path, path_item in SPEC["paths"].items():
        for method, operation in path_item.items():
            if method in METHODS:
                yield path, method, operation


def assert_valid(schema, value, location):
    errors = list(validator(schema).iter_errors(value))
    assert not errors, f"{location}: {[error.message for error in errors]}"


def test_openapi_document_and_design_endpoint_coverage():
    validate(SPEC)
    design = (API_DIR.parent / "backend-design.md").read_text()
    documented = set(re.findall(r"`(GET|POST|PATCH) (/[^` ]+)`", design))
    specified = {(method.upper(), path) for path, method, _ in operations()}
    assert documented <= specified
    assert specified - documented == {("GET", "/health/live"), ("GET", "/health/ready")}


def test_examples_match_schemas():
    for name, schema in SCHEMAS.items():
        for value in schema.get("examples", []):
            assert_valid({"$ref": f"#/components/schemas/{name}"}, value, name)
    for path, method, operation in operations():
        containers = [operation.get("requestBody", {})]
        containers.extend(resolve(SPEC, value) for value in operation["responses"].values())
        for container in containers:
            for media in container.get("content", {}).values():
                examples = [ex["value"] for ex in media.get("examples", {}).values()]
                if "example" in media:
                    examples.append(media["example"])
                for value in examples:
                    assert_valid(media["schema"], value, f"{method} {path}")


def test_security_idempotency_and_truthful_implementation_status():
    public = {
        "/health/live",
        "/health/ready",
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/auth/password/forgot",
        "/auth/password/reset",
    }
    application = FastAPI()
    application.include_router(router)
    live_routes = {
        (method, path.removeprefix("/api/v1"))
        for path, item in application.openapi()["paths"].items()
        for method in item
        if method in METHODS
    }
    for path, method, operation in operations():
        assert (operation.get("security") == []) == (path in public)
        assert SPEC["security"] == [{"bearerAuth": []}]
        implemented = operation["x-implementation-status"] == "implemented"
        assert implemented == ((method, path) in live_routes)
        params = [resolve(SPEC, param) for param in operation.get("parameters", [])]
        keys = [param for param in params if param["name"] == "Idempotency-Key"]
        assert bool(keys) == (method == "post" and not path.startswith("/auth/"))
        if keys:
            assert keys[0]["required"] is True


def test_requests_reject_unknown_fields_and_writing_has_no_500_limit():
    draft = {"revision": 1, "draft": {"skill": "writing", "response_text": "English " * 1000}}
    schema_validator("SaveDraftRequest").validate(draft)
    leaked_owner = {**draft, "user_id": "10000000-0000-4000-8000-000000000001"}
    assert not schema_validator("SaveDraftRequest").is_valid(leaked_owner)
    for name in SCHEMAS:
        if name.endswith("Request"):
            value = copy.deepcopy(SCHEMAS[name]["examples"][0])
            assert not schema_validator(name).is_valid({**value, "unexpected": True}), name


@pytest.mark.parametrize(
    "value",
    [
        {"mode": "custom", "text": " "},
        {"mode": "random", "text": "Travel"},
        {"mode": "catalog"},
        {"mode": "custom", "text": "x" * 201},
    ],
)
def test_invalid_topic_combinations(value):
    assert not schema_validator("TopicSelection").is_valid(value)


def test_answer_exclusivity_and_nullable_draft_clearing():
    qid = "10000000-0000-4000-8000-000000000004"
    option = "10000000-0000-4000-8000-000000000005"
    assert not schema_validator("SubmitAnswerRequest").is_valid({"revision": 1})
    assert not schema_validator("SubmitAnswerRequest").is_valid(
        {
            "revision": 1,
            "selected_option_id": option,
            "response_text": "Answer",
        }
    )
    schema_validator("DraftAnswer").validate(
        {
            "question_id": qid,
            "selected_option_id": None,
            "response_text": None,
        }
    )
    assert not schema_validator("DraftAnswer").is_valid(
        {
            "question_id": qid,
            "selected_option_id": option,
            "response_text": "Answer",
        }
    )


def test_public_exercises_do_not_expose_locked_or_internal_fields():
    forbidden = {
        "is_correct",
        "reference_answer",
        "reference_explanation",
        "evidence_spans",
        "password_hash",
        "rubric_snapshot",
        "behavior_instructions",
        "transcript",
        "storage_key",
        "generator_version",
    }

    def property_names(schema):
        schema = resolve(SPEC, schema)
        result = set(schema.get("properties", {}))
        for child in schema.get("properties", {}).values():
            result |= property_names(child)
        for keyword in ("oneOf", "anyOf", "allOf"):
            for child in schema.get(keyword, []):
                result |= property_names(child)
        if "items" in schema:
            result |= property_names(schema["items"])
        return result

    assert not (property_names(SCHEMAS["Exercise"]) & forbidden)
    assert not (property_names(SCHEMAS["Answer"]) & forbidden)
    user_props = property_names(SCHEMAS["User"])
    assert not (user_props & {"password_hash", "password", "refresh_token_hash"})


def test_postman_export_schema_and_generated_content():
    collection_file = API_DIR / "english-practice.postman_collection.json"
    assert collection_file.read_text() == render_collection()
    official = json.loads(
        (Path(__file__).parent / "fixtures/postman-collection-v2.1.schema.json").read_text()
    )
    collection = json.loads(collection_file.read_text())
    Draft7Validator(official).validate(collection)
    environment = json.loads((API_DIR / "local.postman_environment.json").read_text())
    values = {item["key"]: item for item in environment["values"]}
    for key in ("password", "new_password", "access_token", "refresh_token", "reset_token"):
        assert values[key]["value"] == ""
        assert values[key]["type"] == "secret"


def test_postman_request_templates_match_contract_after_variable_substitution():
    collection = json.loads(render_collection())
    uuid = "10000000-0000-4000-8000-000000000001"
    replacements = {"email": "learner@example.test", "attempt_revision": "1"}
    for folder in collection["item"]:
        for item in folder["item"]:
            request = item["request"]
            path = "/" + "/".join(
                "{" + segment[1:] + "}" if segment.startswith(":") else segment
                for segment in request["url"]["path"]
            )
            operation = SPEC["paths"][path][request["method"].lower()]
            if request.get("body", {}).get("mode") != "raw":
                continue
            raw = re.sub(
                r"\{\{([^}]+)\}\}",
                lambda match: replacements.get(match[1], uuid),
                request["body"]["raw"],
            )
            assert_valid(
                operation["requestBody"]["content"]["application/json"]["schema"],
                json.loads(raw),
                item["name"],
            )
