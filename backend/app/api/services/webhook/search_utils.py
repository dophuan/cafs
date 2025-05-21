import logging
from typing import Dict, Any, List, Union

from sqlalchemy import or_
from app.api.services.conversation.chat import LLMService
from sqlmodel import select, and_
from app.models.item import Item

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SearchUtils:
    @classmethod
    async def parse_and_build_conditions(cls, query: str, llm_service: LLMService) -> List[Any]:
        """Parse natural language query and build search conditions"""
        parsed_result = await llm_service.parse_product_query(query)
        
        if parsed_result["status"] == "error":
            return []
 
        return cls.build_search_conditions(parsed_result["parameters"])

    @staticmethod
    def build_search_conditions(params: Dict[str, Any]) -> List[Any]:
        """Build SQL conditions based on search parameters"""
        conditions = []

        if not params:
            return conditions

        # For category, use OR between terms and add common paint category variations
        if category := params.get('category'):
            category_terms = category.lower().split()
            category_conditions = []
            
            # Paint category variations in Vietnamese
            paint_categories = [
                'sơn', 'sơn nước', 'sơn dầu', 'sơn chống thấm', 
                'sơn nội thất', 'sơn ngoại thất', 'sơn ngoài trời',
                'sơn trong nhà', 'sơn đặc biệt', 'sơn epoxy',
                'sơn lót', 'sơn phủ', 'sơn bóng', 'sơn mờ'
            ]
            
            # Add original search terms
            for term in category_terms:
                category_conditions.append(Item.category.ilike(f"%{term}%"))
                
            # Add relevant paint categories based on search terms
            for paint_cat in paint_categories:
                if any(term in paint_cat for term in category_terms):
                    category_conditions.append(Item.category.ilike(f"%{paint_cat}%"))
            
            if category_conditions:
                conditions.append(or_(*category_conditions))

        # For color, handle common paint color variations
        if color := params.get('color_code'):
            color_lower = color.lower()
            color_conditions = []
            
            # Common color mappings in Vietnamese
            color_mappings = {
                'xanh': ['xanh dương', 'xanh lá', 'xanh biển', 'blue', 'green'],
                'đỏ': ['red', 'đỏ tươi', 'đỏ đô'],
                'vàng': ['yellow', 'vàng nhạt', 'vàng đậm'],
                'trắng': ['white', 'trắng ngà', 'trắng sứ'],
                'đen': ['black', 'đen bóng', 'đen mờ']
            }
            
            # Add original color term
            color_conditions.append(Item.color_code.ilike(f"%{color_lower}%"))
            
            # Add relevant color variations
            for base_color, variations in color_mappings.items():
                if base_color in color_lower:
                    for variation in variations:
                        color_conditions.append(Item.color_code.ilike(f"%{variation}%"))
            
            if color_conditions:
                conditions.append(or_(*color_conditions))

        # Price handling with paint-specific logic
        if price_param := params.get('price'):
            if isinstance(price_param, dict):
                if 'operator' in price_param and 'value' in price_param:
                    try:
                        value = float(price_param['value'])
                        operator_map = {
                            '<': lambda: Item.price < value,
                            '>': lambda: Item.price > value,
                            '<=': lambda: Item.price <= value,
                            '>=': lambda: Item.price >= value,
                            '=': lambda: Item.price == value
                        }
                        if condition := operator_map.get(price_param['operator']):
                            conditions.append(condition())
                    except (ValueError, TypeError):
                        logger.info(f"Invalid price value: {price_param['value']}")

        # Paint-specific specifications handling
        if specs := params.get('specifications'):
            if isinstance(specs, dict):
                paint_specs = {
                    'finish': ['bóng', 'mờ', 'semi-gloss', 'glossy', 'matte'],
                    'base_type': ['nước', 'dầu', 'water-based', 'oil-based'],
                    'usage': ['trong nhà', 'ngoài trời', 'interior', 'exterior'],
                    'coverage': ['độ phủ', 'coverage'],
                    'dry_time': ['thời gian khô', 'dry time']
                }
                
                for key, value in specs.items():
                    if value and key in paint_specs:
                        spec_conditions = []
                        for spec_value in paint_specs[key]:
                            if spec_value.lower() in str(value).lower():
                                spec_conditions.append(
                                    Item.specifications[key].astext.ilike(f"%{spec_value}%")
                                )
                        if spec_conditions:
                            conditions.append(or_(*spec_conditions))

        # Status handling
        if status := params.get('status'):
            if isinstance(status, str) and status.strip():
                conditions.append(Item.status == status.strip())

        # Tags handling with paint-specific tags
        if tags := params.get('tags'):
            paint_tags = ['eco-friendly', 'chống thấm', 'kháng khuẩn', 'chống nấm mốc', 
                        'nhanh khô', 'dễ lau chùi', 'không mùi', 'chống phai màu']
            
            tag_conditions = []
            if isinstance(tags, str) and tags.strip():
                tag_conditions.append(Item.tags.contains([tags.strip()]))
                # Add relevant paint tags
                for paint_tag in paint_tags:
                    if tags.lower() in paint_tag:
                        tag_conditions.append(Item.tags.contains([paint_tag]))
            elif isinstance(tags, list):
                valid_tags = [tag for tag in tags if isinstance(tag, str) and tag.strip()]
                if valid_tags:
                    tag_conditions.append(Item.tags.contains(valid_tags))
                    # Add relevant paint tags
                    for tag in valid_tags:
                        for paint_tag in paint_tags:
                            if tag.lower() in paint_tag:
                                tag_conditions.append(Item.tags.contains([paint_tag]))
            
            if tag_conditions:
                conditions.append(or_(*tag_conditions))

        return conditions

    @staticmethod
    def build_search_query(conditions: List[Any]) -> Any:
        """Build the final search query"""
        statement = select(Item)
        if conditions:
            statement = statement.where(and_(*conditions))
        return statement

    @staticmethod
    def format_items(items: List[Item]) -> List[Dict[str, Any]]:
        """Format item results for response"""
        return [{
            "title": item.title,
            "sku": item.sku,
            "category": item.category,
            "price": f"{item.price:,.0f} VND",
            "quantity": item.quantity,
            "status": "Còn hàng" if item.quantity > 0 else "Hết hàng",
            "specifications": item.specifications,
            "color_code": item.color_code,
            "unit": item.unit,
            "tags": item.tags
        } for item in items]

    @staticmethod
    def build_response_message(items: List[Dict[str, Any]]) -> str:
        """Build formatted response message"""
        message = f"Tìm thấy {len(items)} sản phẩm phù hợp:\n\n"
        return message + "".join(SearchUtils.format_item_message(item) for item in items)

    @staticmethod
    def format_item_message(item: Dict[str, Any]) -> str:
        """Format individual item message"""
        message = f"- {item['title']} (SKU: {item['sku']})\n"
        message += f"  Loại: {item['category']}\n"
        message += f"  Giá: {item['price']}\n"
        message += f"  Trạng thái: {item['status']}\n"
        
        if color := item.get('color_code'):
            message += f"  Màu sắc: {color}\n"
            
        if specs := item.get('specifications'):
            message += SearchUtils.format_specifications_message(specs)
            
        return message + "\n"

    @staticmethod
    def format_specifications_message(specs: Dict[str, Any]) -> str:
        """Format specifications message"""
        spec_translations = {
            'finish': 'Độ hoàn thiện',
            'coverage': 'Độ phủ',
            'dry_time': 'Thời gian khô',
            'base_type': 'Loại gốc'
        }
        
        return "".join(
            f"  {translation}: {specs[key]}\n"
            for key, translation in spec_translations.items()
            if key in specs
        )