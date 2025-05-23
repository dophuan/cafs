import logging
from typing import Any
from app.models.search_params import SearchParams, SearchResult
from sqlmodel import Session
from sqlalchemy import text
from app.core.config import settings
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class VectorSearchService:
    def __init__(self, db: Session):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-ada-002"

    async def get_embedding(self, text: str) -> list[float]:
        """Generate embedding using OpenAI's API"""
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    async def update_product_embedding(self, product: dict[str, Any]) -> None:
        """Update embedding for a single product"""
        try:
            # Combine product fields for embedding
            content = f"{product['title']} {product['description']} {product['category']} {' '.join(product['tags'])}"
            embedding = await self.get_embedding(content)

            # Start a new transaction
            self.db.begin_nested()
            try:
                # Update the product's embedding in the database
                stmt = text("""
                    SELECT update_item_embedding(CAST(:item_id AS UUID), CAST(:embedding AS vector))
                """)
                self.db.execute(
                    stmt,
                    {
                        "item_id": product['id'],
                        "embedding": embedding
                    }
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                raise
                
        except Exception as e:
            logger.error(f"Error updating embedding for product {product['id']}: {str(e)}")
            raise

    async def sync_products_embeddings(self, products: list[dict[str, Any]]) -> dict[str, Any]:
        """Update embeddings for all products"""
        success_count = 0
        failed_count = 0

        for product in products:
            try:
                await self.update_product_embedding(product)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to update embedding for product {product['id']}: {str(e)}")
                failed_count += 1
                continue

        return {
            "status": "success",
            "indexed": success_count,
            "failed": failed_count
        }

    async def search_products(self, search_params: SearchParams) -> SearchResult:
        """Search products using vector similarity"""
        try:
            # Generate embedding for search query
            query_embedding = await self.get_embedding(search_params.query)

            # Build the search query
            stmt = text("""
            SELECT * FROM public.search_items(
                CAST(:query_embedding AS vector),
                :search_text,
                CAST(:price_min AS numeric),
                CAST(:price_max AS numeric),
                CAST(:categories AS text[]),
                CAST(:similarity_threshold AS double precision),
                CAST(:max_results AS integer)
            )
            """)
            
            params = {
                "query_embedding": query_embedding,
                "search_text": search_params.query,
                "price_min": search_params.price_min,
                "price_max": search_params.price_max,
                "categories": search_params.categories,
                "similarity_threshold": 0.7,  # This is a double precision value
                "max_results": search_params.size
            }

            # Execute search
            results = self.db.execute(stmt, params).fetchall()
            
            total = len(results)
            
            return SearchResult(
                total=total,
                page=search_params.page,
                size=search_params.size,
                results=[dict(row) for row in results]
            )

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return SearchResult(
                total=0,
                page=search_params.page,
                size=search_params.size,
                results=[]
            )