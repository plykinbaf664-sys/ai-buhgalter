"""JSON transport edge: reject ambiguous duplicate keys before Pydantic validation."""
import json
from typing import TypeVar

from pydantic import BaseModel

Model = TypeVar("Model", bound=BaseModel)


def _unique_object(pairs):
    # Temporary transport representation only; never exposed to application layers.
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def validate_json(model: type[Model], data: str | bytes | bytearray) -> Model:
    json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    # Strict JSON validation permits JSON-native representations of dates, Decimal
    # and tuples while still rejecting coerced integers/booleans and extra fields.
    return model.model_validate_json(data)
