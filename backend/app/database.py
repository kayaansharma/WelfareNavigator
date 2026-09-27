"""Supabase access helpers. Credentials and storage keys never leave this module."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
_client: Any | None = None
_client_initialized = False

_BOOLEAN_RULE_FIELDS = {
    "is_farmer", "is_student", "is_pregnant", "has_bank_account",
    "has_lpg_connection", "disability", "farmer_status", "student_status",
    "disability_status", "widow_status", "senior_citizen_status",
    "entrepreneur_status",
}
_NUMERIC_RULE_FIELDS = {"age", "annual_family_income", "annual_income", "family_size"}


def get_client() -> Any | None:
    """Return the process-wide Supabase client, or None when it is not configured."""
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
    except Exception as exc:  # configuration/client construction must not stop API startup
        logger.warning("Supabase client could not be initialized (%s)", type(exc).__name__)
        _client = None
    return _client


def set_client_for_tests(client: Any | None, initialized: bool = True) -> None:
    global _client, _client_initialized
    _client, _client_initialized = client, initialized


def _select_all(client: Any, table: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = client.table(table).select("*").range(offset, offset + page_size - 1).execute()
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def _normalize_numeric_string(value: str) -> Any:
    candidate = value.strip()
    try:
        return int(candidate)
    except ValueError:
        try:
            return float(candidate)
        except ValueError:
            return value


def _normalize_rule_value(field: str, operator: str, value: Any) -> Any:
    """Mirror the CSV loader's field-aware typing for values returned by Supabase."""
    if operator == "BETWEEN" and isinstance(value, str) and "-" in value:
        value = [part.strip() for part in value.split("-", 1)]

    if isinstance(value, list):
        # BETWEEN is numeric by definition. IN lists keep category labels as text,
        # while fields with known scalar types retain their CSV-style value types.
        normalize_items = operator == "BETWEEN" or field in _NUMERIC_RULE_FIELDS or field in _BOOLEAN_RULE_FIELDS
        if not normalize_items:
            return value
        return [_normalize_rule_scalar(field, item, numeric=operator == "BETWEEN" or field in _NUMERIC_RULE_FIELDS) for item in value]
    return _normalize_rule_scalar(
        field, value,
        numeric=operator == "BETWEEN" or field in _NUMERIC_RULE_FIELDS,
    )


def _normalize_rule_scalar(field: str, value: Any, *, numeric: bool) -> Any:
    if isinstance(value, str):
        token = value.strip()
        if field in _BOOLEAN_RULE_FIELDS:
            lowered = token.casefold()
            if lowered in {"yes", "true"}:
                return True
            if lowered in {"no", "false"}:
                return False
        if numeric:
            return _normalize_numeric_string(token)
    return value


def _dedupe_value_key(value: Any) -> Any:
    """Create a hashable key that distinguishes booleans from numbers."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, list):
        return ("list", tuple(_dedupe_value_key(item) for item in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((key, _dedupe_value_key(item)) for key, item in value.items())))
    return (type(value).__name__, value)


def check_connection() -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        client.table("schemes").select("id").limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("Supabase connection check failed (%s)", type(exc).__name__)
        return False


def load_catalog(client: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and adapt catalog tables to the backend's existing in-memory shape."""
    client = client or get_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")

    scheme_rows = _select_all(client, "schemes")
    rule_rows = _select_all(client, "eligibility_rules")
    document_rows = _select_all(client, "scheme_documents")
    category_rows = _select_all(client, "scheme_categories")
    profile_rows = _select_all(client, "profiles")
    user_document_rows = _select_all(client, "user_documents")
    if not scheme_rows or not rule_rows or not document_rows or not category_rows:
        raise RuntimeError("Supabase catalog tables are empty or inaccessible")

    rules_by_scheme: dict[str, list[dict[str, Any]]] = {}
    operator_map = {"equals": "==", "greater_than_or_equal": ">=", "less_than_or_equal": "<=", "between": "BETWEEN", "in": "IN"}
    seen_rules: dict[str, set[tuple[Any, ...]]] = {}
    for row in rule_rows:
        scheme_id = str(row["scheme_id"])
        value = row.get("value")
        if isinstance(value, str):
            # Parse serialized containers, but leave scalar strings for the
            # field-aware normalizer (e.g. categorical text "true" stays text).
            import json
            serialized = value.strip()
            if (serialized.startswith(("[", "{")) or
                    (serialized.startswith('"') and serialized.endswith('"'))):
                try:
                    value = json.loads(serialized)
                except (ValueError, TypeError):
                    pass
        operator = operator_map.get(str(row.get("operator") or "==").strip().lower(), str(row.get("operator") or "==").strip().upper())
        value = _normalize_rule_value(str(row.get("field") or ""), operator, value)
        required_value = row.get("required", True)
        required = required_value.strip().casefold() in {"true", "yes", "1"} if isinstance(required_value, str) else bool(required_value)
        group_operator = row.get("group_operator")
        rule = {
            "field": row.get("field"),
            "operator": operator,
            "value": value,
            "description": row.get("description") or f'{row.get("field")} {row.get("operator")} {value}',
            "required": required,
            "group_operator": group_operator,
        }
        duplicate_key = (rule["field"], rule["operator"], _dedupe_value_key(value), required, group_operator)
        seen = seen_rules.setdefault(scheme_id, set())
        if duplicate_key in seen:
            continue
        seen.add(duplicate_key)
        rules_by_scheme.setdefault(scheme_id, []).append(rule)

    documents_by_scheme: dict[str, list[dict[str, Any]]] = {}
    for row in document_rows:
        scheme_id = str(row["scheme_id"])
        document_type = row.get("document_type") or "Document"
        required = row.get("required", True) not in (False, 0, "false", "False", "0")
        documents_by_scheme.setdefault(scheme_id, []).append({
            "name": document_type,
            "type": document_type,
            "requirement_level": "Required" if required else "Optional",
            "required": required,
            "notes": "",
        })

    schemes: list[dict[str, Any]] = []
    for row in scheme_rows:
        scheme_id = str(row["id"])
        schemes.append({
            **row,
            "id": scheme_id,
            "name": row.get("name") or scheme_id,
            "description": row.get("description") or row.get("eligibility_summary") or "",
            "government": row.get("government") or row.get("government_level") or "Not specified",
            "ministry": row.get("ministry") or "Not specified",
            "state": row.get("state") or "All India",
            "category": row.get("category") or "General Welfare",
            "benefits": row.get("benefits") or "",
            "eligibility_summary": row.get("eligibility_summary") or row.get("description") or "",
            "application_process": row.get("application_process") or "Review current guidance at the official portal.",
            "application_url": row.get("application_url") or row.get("source_url") or "https://www.india.gov.in/",
            "source_url": row.get("source_url") or row.get("application_url") or "https://www.india.gov.in/",
            "source_name": row.get("source_name") or "Official scheme source",
            "last_verified": str(row.get("last_verified") or ""),
            "active": row.get("active", True),
            "synthetic": row.get("synthetic", False),
            "rules": rules_by_scheme.get(scheme_id, []),
            "documents": documents_by_scheme.get(scheme_id, []),
        })

    demo_users: list[dict[str, Any]] = []
    demo_id_to_uuid: dict[str, str] = {}
    for row in profile_rows:
        attributes = row.get("attributes") or {}
        if not isinstance(attributes, dict):
            continue
        demo_id = attributes.get("user_id")
        if not demo_id:
            continue
        demo_id = str(demo_id)
        demo_id_to_uuid[demo_id] = str(row.get("user_id"))
        demo_users.append({"user_id": demo_id, "name": attributes.get("name") or demo_id, **attributes})

    demo_documents: list[dict[str, Any]] = []
    uuid_to_demo_id = {uuid: demo_id for demo_id, uuid in demo_id_to_uuid.items()}
    for row in user_document_rows:
        demo_id = uuid_to_demo_id.get(str(row.get("user_id")))
        if not demo_id:
            continue
        demo_documents.append({
            "user_id": demo_id,
            "user_document_id": str(row.get("id", "")),
            "document_name": row.get("filename") or "Document",
            "content_type": row.get("content_type"),
            "status": row.get("status") or "NEEDS_REVIEW",
            "created_at": row.get("created_at"),
        })

    categories = [{
        "category_id": row.get("category_id"),
        "category_name": row.get("category_name"),
        "description": row.get("description"),
    } for row in category_rows]
    return schemes, demo_users, demo_documents, categories


def profile_by_demo_id(demo_id: str, client: Any | None = None) -> dict[str, Any] | None:
    client = client or get_client()
    if client is None:
        return None
    for row in _select_all(client, "profiles"):
        attributes = row.get("attributes") or {}
        if isinstance(attributes, dict) and str(attributes.get("user_id", "")) == demo_id:
            return {**row, "attributes": attributes}
    return None


def documents_for_user(user_uuid: str, client: Any | None = None) -> list[dict[str, Any]]:
    client = client or get_client()
    if client is None:
        return []
    response = client.table("user_documents").select("id,user_id,filename,content_type,status,created_at").eq("user_id", user_uuid).execute()
    return [{
        "id": str(row.get("id", "")), "filename": row.get("filename") or "Document",
        "type": row.get("filename") or "Document", "content_type": row.get("content_type"),
        "status": row.get("status") or "NEEDS_REVIEW", "created_at": row.get("created_at"),
        "demo": True, "note": "Stored as user document metadata; document authenticity is not verified.",
    } for row in (response.data or [])]


def save_profile(user_uuid: str, profile: dict[str, Any], client: Any | None = None) -> None:
    client = client or get_client()
    if client is None:
        return
    attributes = {key: value for key, value in profile.items() if not key.startswith("_") and key not in {"existing_benefits"}}
    statuses = profile.get("_statuses", {})
    client.table("profiles").update({"attributes": attributes, "field_status": statuses, "language": profile.get("language", "English")}).eq("user_id", user_uuid).execute()


def add_user_document(user_uuid: str, filename: str, content_type: str, status: str,
                      client: Any | None = None) -> dict[str, Any] | None:
    """Persist document metadata only. File bytes remain in the existing local processing flow."""
    client = client or get_client()
    if client is None:
        return None
    response = client.table("user_documents").insert({
        "user_id": user_uuid,
        "filename": filename,
        "private_storage_key": "local-processing-only://metadata",
        "content_type": content_type,
        "status": status,
    }).execute()
    return (response.data or [None])[0]


def update_user_document(document_id: str, values: dict[str, Any], client: Any | None = None) -> None:
    client = client or get_client()
    if client is None:
        return
    # Select only columns used by the API; never select or return the storage key.
    client.table("user_documents").update(values).eq("id", document_id).execute()
