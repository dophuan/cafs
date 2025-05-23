from typing import List, Optional
from sqlalchemy.types import UserDefinedType
from sqlalchemy.dialects.postgresql.base import ischema_names

class VECTOR(UserDefinedType):
    cache_ok = True

    def __init__(self, dim=1536):
        self.dim = dim

    def get_col_spec(self, **kw):
        return f"vector({self.dim})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return f"[{','.join(str(x) for x in value)}]"
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            if isinstance(value, str) and value.startswith('[') and value.endswith(']'):
                return [float(x) for x in value[1:-1].split(',')]
            return list(value)
        return process

    def python_type(self):
        return List[float]

# Register the type
if 'vector' not in ischema_names:
    ischema_names['vector'] = VECTOR