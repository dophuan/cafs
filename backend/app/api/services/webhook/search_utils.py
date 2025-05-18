from typing import Dict, Any, List, Union
from sqlmodel import select, and_
from app.models.item import Item

class SearchUtils:
    @staticmethod
    def build_search_conditions(params: Dict[str, Any]) -> List[Any]:
        """Build SQL conditions based on search parameters"""
        conditions = []
        
        # Basic text fields
        text_fields = {
            'title': Item.title,
            'description': Item.description,
            'sku': Item.sku,
            'category': Item.category,
            'color_code': Item.color_code,
            'unit': Item.unit,
            'barcode': Item.barcode,
            'supplier_id': Item.supplier_id
        }
        
        for field, column in text_fields.items():
            if value := params.get(field):
                conditions.append(column.ilike(f"%{value}%"))

        # Numeric comparisons
        numeric_fields = {
            'price': Item.price,
            'quantity': Item.quantity,
            'reorder_point': Item.reorder_point,
            'max_stock': Item.max_stock
        }
        
        for field, column in numeric_fields.items():
            if value := params.get(field):
                conditions.extend(
                    SearchUtils.build_numeric_conditions(column, value)
                )

        # Special fields
        if specs := params.get('specifications'):
            conditions.extend(
                SearchUtils.build_specification_conditions(specs)
            )
            
        if tags := params.get('tags'):
            conditions.extend(
                SearchUtils.build_tag_conditions(tags)
            )
            
        if status := params.get('status'):
            conditions.append(Item.status == status)

        return conditions

    @staticmethod
    def build_numeric_conditions(column: Any, value: Dict[str, Any]) -> List[Any]:
        """Build conditions for numeric fields"""
        conditions = []
        
        if isinstance(value, dict):
            if 'min' in value and 'max' in value:
                conditions.append(column.between(value['min'], value['max']))
            elif 'min' in value:
                conditions.append(column >= value['min'])
            elif 'max' in value:
                conditions.append(column <= value['max'])
            elif 'value' in value and 'operator' in value:
                operator_map = {
                    '<': column < value['value'],
                    '>': column > value['value'],
                    '<=': column <= value['value'],
                    '>=': column >= value['value'],
                    '=': column == value['value']
                }
                if condition := operator_map.get(value['operator']):
                    conditions.append(condition)
                    
        return conditions

    @staticmethod
    def build_specification_conditions(specs: Dict[str, Any]) -> List[Any]:
        """Build conditions for specification fields"""
        return [
            Item.specifications[key].astext.ilike(f"%{value}%")
            for key, value in specs.items()
        ]

    @staticmethod
    def build_tag_conditions(tags: Union[str, List[str]]) -> List[Any]:
        """Build conditions for tags array field"""
        if isinstance(tags, str):
            return [Item.tags.contains([tags])]
        return [Item.tags.contains([tag]) for tag in tags]

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
            "dimensions": item.dimensions,
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
        message += f"  Số lượng: {item['quantity']} {item['unit']}\n"
        message += f"  Trạng thái: {item['status']}\n"
        
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