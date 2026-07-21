from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect


def model_dict(model: Any, *, camel: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in inspect(model).mapper.column_attrs:
        key = column.key
        value = getattr(model, key)
        if isinstance(value, datetime | date):
            value = value.isoformat()
        output_key = snake_to_camel(key) if camel else key
        data[output_key] = value
    return data


def snake_to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)
