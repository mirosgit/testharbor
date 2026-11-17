from typing import Any


def ids(case_list: dict[str, Any], field: str = "id") -> list[Any]:
    """Extract one field from a CaseList response, in order."""
    return [c[field] for c in case_list["items"]]
