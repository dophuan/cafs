from typing import Any

from app.models.search_params import SearchParams


class QueryBuilder:
    @staticmethod
    def build_search_query(params: SearchParams) -> dict[str, Any]:
        must_conditions = []
        should_conditions = []
        filter_conditions = []

        # Handle main query text
        if params.query:
            must_conditions.append(
                {
                    "multi_match": {
                        "query": params.query,
                        "fields": [
                            "title^3",
                            "description^2",
                            "category^2",
                            "color_code",
                            "specifications.*",
                        ],
                        "type": "most_fields",
                        "operator": "and",
                        "fuzziness": "AUTO",
                    }
                }
            )

        # Category matching
        if params.category:
            must_conditions.append(
                {
                    "match": {
                        "category": {
                            "query": params.category,
                            "operator": "and",  # Changed to 'and' for exact category matching
                        }
                    }
                }
            )

        # Color matching
        if params.color:
            must_conditions.append(
                {  # Changed from should to must for color
                    "match": {
                        "color_code": {
                            "query": params.color,
                            "operator": "and",  # Changed to 'and' for exact color matching
                        }
                    }
                }
            )

        # Price range handling
        if params.price_range:
            range_query = {}
            if "min" in params.price_range:
                range_query["gte"] = float(params.price_range["min"])
            if "max" in params.price_range:
                range_query["lte"] = float(params.price_range["max"])
            if range_query:
                filter_conditions.append({"range": {"price": range_query}})

        # Specifications matching
        if params.specifications:
            for key, value in params.specifications.items():
                must_conditions.append(
                    {
                        "match": {
                            f"specifications.{key}": {"query": value, "operator": "and"}
                        }
                    }
                )

        # Status filter
        if params.status:
            filter_conditions.append({"term": {"status.keyword": params.status}})

        query = {
            "query": {"bool": {"must": must_conditions, "filter": filter_conditions}},
            "from": (params.page - 1) * params.size,
            "size": params.size,
            "_source": True,
            "sort": [{"_score": "desc"}, {"price": "asc"}],
        }

        # Only add should if we have conditions
        if should_conditions:
            query["query"]["bool"]["should"] = should_conditions
            query["query"]["bool"]["minimum_should_match"] = 1

        return query
