ELASTICSEARCH_MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "vietnamese_analyzer": {
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "vietnamese_stop",
                        "vietnamese_normalize"
                    ]
                }
            },
            "filter": {
                "vietnamese_stop": {
                    "type": "stop",
                    "stopwords": ["và", "hoặc", "với", "trong", "ngoài", "cho"]
                },
                "vietnamese_normalize": {
                    "type": "asciifolding"
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "title": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword"
                    }
                }
            },
            "description": {
                "type": "text",
                "analyzer": "vietnamese_analyzer"
            },
            "category": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword"
                    }
                }
            },
            "color_code": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword"
                    }
                }
            },
            "price": {
                "type": "float"
            },
            "specifications": {
                "type": "object",
                "properties": {
                    "finish": {"type": "keyword"},
                    "coverage": {"type": "keyword"},
                    "dry_time": {"type": "keyword"},
                    "base_type": {"type": "keyword"}
                }
            },
            "tags": {
                "type": "keyword"
            },
            "status": {
                "type": "keyword"
            },
            "quantity": {
                "type": "integer"
            },
            "reorder_point": {
                "type": "integer"
            },
            "sku": {
                "type": "keyword"
            },
            "barcode": {
                "type": "keyword"
            }
        }
    }
}