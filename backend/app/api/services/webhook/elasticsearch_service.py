from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import Dict, Any, List
import logging

from app.api.constants.mappings import ELASTICSEARCH_MAPPING
from app.models.search_params import SearchParams, SearchResult
from app.query_builder import QueryBuilder
from app.core.config import settings

logger = logging.getLogger(__name__)

class ElasticSearchService:
    def __init__(self, hosts: List[str] = None):
        if hosts is None:
            elasticsearch_host = settings.ELASTICSEARCH_HOST or 'localhost'
            hosts = [f'http://{elasticsearch_host}:9200']
        
        self.client = Elasticsearch(
            hosts,
            request_timeout=30
        )
        self.index_name = 'products'

    async def setup_index(self) -> None:
        """Create index with mapping if it doesn't exist"""
        try:
            if not self.client.indices.exists(index=self.index_name):
                self.client.indices.create(
                    index=self.index_name,
                    body=ELASTICSEARCH_MAPPING  # Use the complete mapping directly
                )
                logger.info(f"Created index {self.index_name}")
            else:
                logger.debug(f"Index {self.index_name} already exists")
        except Exception as e:
            logger.error(f"Failed to setup index: {str(e)}")
            raise

    async def index_products(self, products: List[Dict[str, Any]]) -> Dict[str, int]:
        try:
            if not products:
                logger.warning("No products to index")
                return {'indexed': 0, 'failed': 0}

            logger.info(f"Preparing to index {len(products)} products")
            logger.info(f"Sample product: {products[0]}")  # Add this to see data structure
            
            actions = []
            for product in products:
                try:
                    action = {
                        '_index': self.index_name,
                        '_source': {
                            'title': str(product.get('title', '')),
                            'description': str(product.get('description', '')),
                            'category': str(product.get('category', '')),
                            'color_code': str(product.get('color_code', '')),
                            'price': float(product.get('price', 0)),
                            'specifications': dict(product.get('specifications', {})),
                            'tags': list(product.get('tags', [])),
                            'status': str(product.get('status', '')),
                            'sku': str(product.get('sku', '')),
                            'quantity': int(product.get('quantity', 0))
                        }
                    }
                    actions.append(action)
                except Exception as e:
                    logger.error(f"Error preparing product for indexing: {str(e)}")
                    logger.error(f"Problematic product: {product}")

            logger.info(f"Created {len(actions)} actions for bulk indexing")
            
            # Add debug log for first action
            if actions:
                logger.info(f"Sample action: {actions[0]}")

            # First, delete existing index
            if self.client.indices.exists(index=self.index_name):
                self.client.indices.delete(index=self.index_name)
                logger.info("Deleted existing index")
            
            # Recreate index with mapping
            await self.setup_index()
            logger.info("Created new index with mapping")
            
            # Bulk index with refresh
            success, failed = bulk(
                self.client, 
                actions, 
                refresh=True
            )
            logger.info(f"Bulk indexing complete: {success} succeeded, {failed} failed")
            await self.debug_index()
            # Add more detailed verification
            count = self.client.count(index=self.index_name)
            logger.info(f"Final index count: {count['count']}")
            
            # Add sample document check
            sample = self.client.search(
                index=self.index_name,
                body={"query": {"match_all": {}}, "size": 1}
            )
            if sample['hits']['hits']:
                logger.info(f"Sample indexed document: {sample['hits']['hits'][0]['_source']}")
            
            return {'indexed': success, 'failed': failed}
            
        except Exception as e:
            logger.error(f"Indexing error: {str(e)}", exc_info=True)
            return {'indexed': 0, 'failed': len(products) if products else 0}
        
    async def debug_index(self) -> None:
        """Debug index mapping and settings"""
        try:
            # Check if index exists
            exists = self.client.indices.exists(index=self.index_name)
            logger.info(f"Index {self.index_name} exists: {exists}")
            
            if exists:
                # Get mapping
                mapping = self.client.indices.get_mapping(index=self.index_name)
                logger.info(f"Index mapping: {mapping}")
                
                # Get settings
                settings = self.client.indices.get_settings(index=self.index_name)
                logger.info(f"Index settings: {settings}")
                
                # Get count
                count = self.client.count(index=self.index_name)
                logger.info(f"Document count: {count}")
                
                # Get a sample document
                sample = self.client.search(
                    index=self.index_name,
                    body={
                        "query": {"match_all": {}},
                        "size": 1
                    }
                )
                logger.info(f"Sample search result: {sample}")
        except Exception as e:
            logger.error(f"Debug error: {str(e)}")


    async def search_products(self, search_params: SearchParams) -> SearchResult:
        """Execute search query based on search parameters"""
        try:
            await self.debug_index()
            if not self.client.indices.exists(index=self.index_name):
                await self.setup_index()
                logger.warning("Index did not exist, created it")
                return SearchResult(
                    total=0,
                    page=search_params.page,
                    size=search_params.size,
                    results=[]
                )

            query_body = QueryBuilder.build_search_query(search_params)
            logger.info(f"Executing search with query: {query_body}")
            
            response = self.client.search(
                index=self.index_name,
                body=query_body
                # Remove size and from_ parameters as they should be in query_body
            )
            
            hits = response['hits']['hits']
            total = response['hits']['total']['value']
            
            logger.debug(f"Search returned {total} total hits")
            
            results = [{
                'id': hit['_id'],
                'score': hit['_score'],
                **hit['_source']
            } for hit in hits]

            return SearchResult(
                total=total,
                page=search_params.page,
                size=search_params.size,
                results=results
            )

        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return SearchResult(
                total=0,
                page=search_params.page,
                size=search_params.size,
                results=[]
            )