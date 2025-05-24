ELASTICSEARCH_MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "vietnamese_analyzer": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "vietnamese_stop", "vietnamese_normalize"],
                }
            },
            "filter": {
                "vietnamese_stop": {
                    "type": "stop",
                    "stopwords": ["và", "hoặc", "với", "trong", "ngoài", "cho"],
                },
                "vietnamese_normalize": {"type": "asciifolding"},
            },
        }
    },
    "mappings": {
        "properties": {
            "title": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "description": {"type": "text", "analyzer": "vietnamese_analyzer"},
            "category": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "color_code": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "price": {"type": "float"},
            "specifications": {
                "type": "object",
                "properties": {
                    "finish": {"type": "keyword"},
                    "coverage": {"type": "keyword"},
                    "dry_time": {"type": "keyword"},
                    "base_type": {"type": "keyword"},
                },
            },
            "tags": {"type": "keyword"},
            "status": {"type": "keyword"},
            "quantity": {"type": "integer"},
            "reorder_point": {"type": "integer"},
            "sku": {"type": "keyword"},
            "barcode": {"type": "keyword"},
        }
    },
}

SUPABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    title TEXT,
    description TEXT,
    category TEXT,
    color_code TEXT,
    price NUMERIC(10, 2),
    specifications JSONB,
    tags TEXT[], -- Array of strings for tags
    status TEXT,
    quantity INTEGER,
    reorder_point INTEGER,
    sku TEXT UNIQUE,
    barcode TEXT UNIQUE,
    embedding VECTOR(1536), -- pgvector column for OpenAI embeddings
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create a full-text search index for Vietnamese language
CREATE EXTENSION IF NOT EXISTS unaccent; -- For normalization
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- For trigram-based similarity search

CREATE INDEX IF NOT EXISTS idx_products_title_description ON products USING GIN (
    to_tsvector('vietnamese', title || ' ' || description)
);

CREATE INDEX IF NOT EXISTS idx_products_embedding ON products USING ivfflat (embedding) WITH (lists = 100);

-- Add triggers to update `updated_at` automatically
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_updated_at ON products;
CREATE TRIGGER trg_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
"""