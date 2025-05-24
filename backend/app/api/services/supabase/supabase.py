import logging
from typing import Any, List

from openai import OpenAI
from supabase import create_client, Client
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from app.api.constants.mappings import SUPABASE_SCHEMA
from app.core.config import settings
from app.models.search_params import SearchParams, SearchResult

logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self):
        self.client = self._get_client()
        self.table_name = settings.SUPABASE_TABLE or "item"
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"Service initialized with table: {self.table_name}")

    def _get_client(self) -> Any:
        """
        Initialize the appropriate client based on the environment.
        - Use SQLAlchemy for local PostgreSQL.
        - Use Supabase client for production.
        """
        try:
            if settings.ENVIRONMENT == "production":
                logger.info("Initializing Supabase client for production...")
                return create_client(settings.POSTGRES_SERVER, settings.SUPABASE_API_KEY)
            elif settings.ENVIRONMENT == "local":
                logger.info("Initializing SQLAlchemy engine for local PostgreSQL...")
                connection_string = str(settings.SQLALCHEMY_DATABASE_URI)
                return create_engine(connection_string, echo=True)
            else:
                logger.info(f"Initializing Supabase client for {settings.ENVIRONMENT}...")
                return create_client(settings.POSTGRES_SERVER, settings.SUPABASE_API_KEY)
        except Exception as e:
            logger.error(f"Error initializing database client: {str(e)}", exc_info=True)
            raise

    def _execute_query(self, query: str, params: dict = None) -> List[Any]:
        """
        Execute a query using the SQLAlchemy engine.
        """
        if settings.ENVIRONMENT == "local":
            try:
                logger.info(f"Executing query: {query}")
                with self.client.begin() as connection:  # Explicit transaction
                    result = connection.execute(text(query), params or {})
                    if query.strip().lower().startswith("select"):
                        return result.fetchall()
                    return []
            except Exception as e:
                logger.error(f"Error executing query: {query}, params: {params}, error: {str(e)}", exc_info=True)
                raise
        else:
            logger.error("Query execution is only available for local PostgreSQL.")
            raise NotImplementedError("Direct query execution is not supported in production.")

    async def setup_table(self) -> None:
        try:
            logger.info("==== Running local db setup ====")

            # Enable vector extension
            self._execute_query("CREATE EXTENSION IF NOT EXISTS vector;")
            logger.info("`vector` extension is ready.")

            # Create the `user` table
            self._execute_query("""
            CREATE TABLE IF NOT EXISTS public."user" (
                id UUID PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                is_superuser BOOLEAN DEFAULT FALSE,
                full_name VARCHAR(255),
                hashed_password VARCHAR(255) NOT NULL
            );
            """)
            logger.info("Table 'user' is ready.")

            # Create the `item` table
            self._execute_query("""
            CREATE TABLE IF NOT EXISTS public.item (
                id UUID PRIMARY KEY,
                owner_id UUID NOT NULL REFERENCES public."user"(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                color_code TEXT,
                price NUMERIC(10, 2),
                quantity INT,
                dimensions JSONB,
                specifications JSONB,
                tags TEXT[],
                sku TEXT UNIQUE,
                status TEXT DEFAULT 'active',
                reorder_point INT,
                max_stock INT,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                embedding VECTOR(1536),
                unit VARCHAR(20),
                barcode VARCHAR(100),
                supplier_id VARCHAR(100)
            );
            """)
            logger.info("Table 'item' is ready.")
        except Exception as e:
            logger.error(f"Failed to setup tables: {str(e)}", exc_info=True)
            raise

    async def index_products(self, products: List[dict[str, Any]]) -> dict[str, int]:
        """
        Index products into the database, generating embeddings for vector search.
        """
        try:
            if not products:
                logger.warning("No products to index.")
                return {"indexed": 0, "failed": 0}

            logger.info(f"Preparing to index {len(products)} products.")
            indexed, failed = 0, 0

            for product in products:
                try:
                    # Generate embeddings for the product title and description
                    text = f"{product.get('title', '')} {product.get('description', '')}"
                    embedding = await self.get_embeddings(text)

                    if settings.ENVIRONMENT == "local":
                        # Insert product into local PostgreSQL
                        query = f"""
                        INSERT INTO {self.table_name} (
                            title, description, category, color_code, price,
                            specifications, tags, status, sku, quantity, embedding
                        ) VALUES (
                            :title, :description, :category, :color_code, :price,
                            :specifications, :tags, :status, :sku, :quantity, 
                            :embedding::vector(1536)
                        )
                        """
                        params = {
                            "title": product.get("title", ""),
                            "description": product.get("description", ""),
                            "category": product.get("category", ""),
                            "color_code": product.get("color_code", ""),
                            "price": float(product.get("price", 0)),
                            "specifications": product.get("specifications", {}),
                            "tags": product.get("tags", []),
                            "status": product.get("status", ""),
                            "sku": product.get("sku", ""),
                            "quantity": int(product.get("quantity", 0)),
                            "embedding": embedding,
                        }
                        self._execute_query(query, params)
                        indexed += 1
                    else:
                        # Insert product into Supabase
                        try:
                            data = {
                                "title": product.get("title", ""),
                                "description": product.get("description", ""),
                                "category": product.get("category", ""),
                                "color_code": product.get("color_code", ""),
                                "price": float(product.get("price", 0)),
                                "specifications": product.get("specifications", {}),
                                "tags": product.get("tags", []),
                                "status": product.get("status", ""),
                                "sku": product.get("sku", ""),
                                "quantity": int(product.get("quantity", 0)),
                                "embedding": embedding
                            }
                            
                            response = self.client.table(self.table_name).insert(data).execute()
                            
                            if hasattr(response, 'data'):
                                if response.data:
                                    indexed += 1
                                else:
                                    logger.error(f"Failed to index product into Supabase: {product.get('title')} - No data returned")
                                    failed += 1
                            else:
                                logger.error(f"Failed to index product into Supabase: {product.get('title')} - Invalid response")
                                failed += 1
                                
                        except Exception as supabase_error:
                            logger.error(f"Supabase insertion error for product {product.get('title')}: {str(supabase_error)}")
                            failed += 1

                except Exception as product_error:
                    logger.error(f"Error processing product {product.get('title')}: {str(product_error)}")
                    failed += 1

            logger.info(f"Indexing complete: {indexed} succeeded, {failed} failed.")
            return {"indexed": indexed, "failed": failed}
            
        except Exception as e:
            logger.error(f"Critical indexing error: {str(e)}", exc_info=True)
            return {"indexed": 0, "failed": len(products) if products else 0}

    async def get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for a given text using OpenAI."""
        try:
            if not text:
                logger.warning("Empty text provided for embeddings")
                return []
                
            logger.info(f"Generating embeddings for text: {text[:100]}...")
            
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            
            if not response.data:
                logger.warning("No embeddings returned from API")
                return []
                
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}", exc_info=True)
            raise

    async def search_products(self, search_params: SearchParams) -> SearchResult:
        """Search products based on search parameters."""
        try:
            # Construct search text
            search_parts = []
            if search_params.query:
                search_parts.append(search_params.query)
            if search_params.category:
                search_parts.append(f"category: {search_params.category}")
            if search_params.color:
                search_parts.append(f"color: {search_params.color}")
            if search_params.specifications:
                specs_str = " ".join(f"{k}: {v}" for k, v in search_params.specifications.items())
                search_parts.append(f"specifications: {specs_str}")
            
            search_text = " ".join(search_parts)
            
            # Get embeddings for search text
            embedding = await self.get_embeddings(search_text)
            
            if not embedding:
                logger.warning("No embeddings generated for search parameters")
                return SearchResult(
                    total=0,
                    page=search_params.page,
                    size=search_params.size,
                    results=[]
                )

            # Build the query with proper vector handling
            query = """
            WITH vector_matches AS (
                SELECT id, embedding <-> array[{}]::vector(1536) as distance
                FROM {}
                WHERE 1=1
            """.format(
                ','.join(str(x) for x in embedding),
                self.table_name
            )

            # Add filters
            if search_params.category:
                query += " AND category = '{}'".format(search_params.category.replace("'", "''"))
            if search_params.status:
                query += " AND status = '{}'".format(search_params.status.replace("'", "''"))
            
            # Close the CTE and get final results
            query += """
            )
            SELECT i.*, vm.distance
            FROM {} i
            INNER JOIN vector_matches vm ON vm.id = i.id
            WHERE vm.distance <= 0.3
            ORDER BY vm.distance
            LIMIT {}
            OFFSET {}
            """.format(
                self.table_name,
                search_params.size,
                (search_params.page - 1) * search_params.size
            )

            logger.info(f"Executing search query: {query}")
            
            results = self._execute_query(query)
            total = len(results)
            
            logger.info(f"Found {total} results for search query")
            
            return SearchResult(
                total=total,
                page=search_params.page,
                size=search_params.size,
                results=results,
            )
        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return SearchResult(
                total=0, 
                page=search_params.page,
                size=search_params.size,
                results=[]
            )