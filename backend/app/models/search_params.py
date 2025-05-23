# app/models/search_params.py
from dataclasses import dataclass
from typing import Any


@dataclass
class SearchParams:
    query: str | None = None
    category: str | None = None
    color: str | None = None
    price_range: dict[str, float] | None = None
    specifications: dict[str, Any] | None = None
    status: str | None = None
    page: int = 1
    size: int = 10

    @classmethod
    def from_parsed_params(cls, parsed_params: dict[str, Any]) -> "SearchParams":
        """Create SearchParams from parsed LLM parameters"""
        # Extract price range
        price_range = {}
        price_param = parsed_params.get("price")
        if price_param and isinstance(price_param, dict):
            if price_param.get("operator") == "<":
                price_range["max"] = float(price_param["value"])
            elif price_param.get("operator") == ">":
                price_range["min"] = float(price_param["value"])
            elif price_param.get("operator") == "between":
                price_range["min"] = float(price_param.get("min", 0))
                price_range["max"] = float(price_param.get("max", 0))

        return cls(
            query=parsed_params.get("query"),
            category=parsed_params.get("category"),
            color=parsed_params.get("color_code"),
            price_range=price_range if price_range else None,
            specifications=parsed_params.get("specifications"),
            status=parsed_params.get("status"),
        )


@dataclass
class SearchResult:
    total: int
    page: int
    size: int
    results: list[dict[str, Any]]
