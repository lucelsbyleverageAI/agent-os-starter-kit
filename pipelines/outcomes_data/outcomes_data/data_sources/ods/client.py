from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from outcomes_data.utils.http import build_retrying_session


@dataclass
class OdsSettings:
    base_url: str = "https://sandbox.api.service.nhs.uk/organisation-data-terminology-api"
    api_key: Optional[str] = None


class OdsClient:
    def __init__(self, settings: OdsSettings) -> None:
        self.settings = settings
        self.session = build_retrying_session()

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/fhir+json"}
        if self.settings.api_key:
            # Some deployments expect `apikey`, others `Authorization: Bearer`
            headers["apikey"] = self.settings.api_key
        return headers

    def fetch_organizations_by_role(self, role_code: str, count: int = 1000) -> Iterable[dict]:
        """Yield FHIR Organization resources for a given role_code, paginated by _offset.

        The sandbox supports `_count` and `_offset` query params.
        """
        offset = 0
        if count > 1000:
            count = 1000  # API typically enforces a hard max
        while True:
            params = {"roleCode": role_code, "_count": str(count), "_offset": str(offset)}
            url = f"{self.settings.base_url}/fhir/Organization"
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("entry", [])
            if not entries:
                break
            for e in entries:
                res = e.get("resource") or {}
                if res.get("resourceType") == "Organization":
                    yield res
            if len(entries) < count:
                break
            offset += count


def _get_extension(resource: dict, url: str) -> Optional[dict]:
    for ext in resource.get("extension", []) or []:
        if ext.get("url") == url:
            return ext
    return None


def _ext_value(ext: dict, suburl: str) -> Optional[dict]:
    for e in ext.get("extension", []) or []:
        if e.get("url") == suburl:
            return e
    return None


def parse_organization(org: dict, matched_role_code: str | None = None, matched_role_display: str | None = None) -> dict:
    """Flatten essential fields from a FHIR Organization into a row dict."""
    org_code = org.get("id") or _first_identifier_value(org)
    name = org.get("name")
    active = org.get("active")

    role_ext = _get_extension(org, "https://fhir.nhs.uk/England/StructureDefinition/Extension-England-OrganisationRole")
    primary_role_code = None
    primary_role_display = None
    if role_ext:
        rc = _ext_value(role_ext, "roleCode") or {}
        vcc = (rc.get("valueCodeableConcept") or {}).get("coding") or []
        if vcc:
            primary_role_code = vcc[0].get("code")
            primary_role_display = vcc[0].get("display")
    # capture all roles present (primary + others) if available
    roles_json = []
    if role_ext:
        rc = _ext_value(role_ext, "roleCode") or {}
        vcc = (rc.get("valueCodeableConcept") or {}).get("coding") or []
        for c in vcc:
            roles_json.append({"code": c.get("code"), "display": c.get("display")})

    last_change = None
    tdt = _get_extension(org, "https://fhir.nhs.uk/England/StructureDefinition/Extension-England-TypedDateTime")
    if tdt:
        dt = _ext_value(tdt, "dateTime")
        if dt and "valueDateTime" in dt:
            last_change = dt.get("valueDateTime")

    phone = None
    website = None
    for tel in org.get("telecom", []) or []:
        if tel.get("system") == "phone" and not phone:
            phone = tel.get("value")
        if tel.get("system") == "url" and not website:
            website = tel.get("value")

    address_json = org.get("address")

    # foundation trust flag via non-primary role RO57
    is_foundation_trust = any((r.get("code") == "RO57") for r in roles_json)

    return {
        "org_code": org_code,
        "org_name": name,
        "primary_role_code": primary_role_code,
        "primary_role_display": primary_role_display,
        "matched_role_code": matched_role_code or primary_role_code,
        "matched_role_display": matched_role_display,
        "is_foundation_trust": is_foundation_trust,
        "active": active,
        "last_change_date": last_change,
        "address_json": address_json,
        "roles_json": roles_json,
        "phone": phone,
        "website": website,
    }


def _first_identifier_value(org: dict) -> Optional[str]:
    ids = org.get("identifier", []) or []
    for ident in ids:
        if ident.get("value"):
            return ident.get("value")
    return None
