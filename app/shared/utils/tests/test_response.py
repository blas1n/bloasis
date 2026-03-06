"""Tests for CamelJSONResponse — snake_case to camelCase conversion."""

import json
from decimal import Decimal

from app.shared.utils.response import CamelJSONResponse, _convert, _to_camel


class TestToCamel:
    def test_simple(self):
        assert _to_camel("snake_case") == "snakeCase"

    def test_single_word(self):
        assert _to_camel("name") == "name"

    def test_multiple_underscores(self):
        assert _to_camel("total_return_amount") == "totalReturnAmount"

    def test_empty_string(self):
        assert _to_camel("") == ""

    def test_already_camel(self):
        assert _to_camel("camelCase") == "camelCase"


class TestConvert:
    def test_flat_dict(self):
        result = _convert({"user_id": "123", "first_name": "Alice"})
        assert result == {"userId": "123", "firstName": "Alice"}

    def test_nested_dict(self):
        result = _convert({"user_info": {"first_name": "Alice", "last_name": "Bob"}})
        assert result == {"userInfo": {"firstName": "Alice", "lastName": "Bob"}}

    def test_list_of_dicts(self):
        result = _convert([{"order_id": "1"}, {"order_id": "2"}])
        assert result == [{"orderId": "1"}, {"orderId": "2"}]

    def test_decimal_to_string(self):
        result = _convert({"total_value": Decimal("150.25")})
        assert result == {"totalValue": "150.25"}

    def test_mixed_types(self):
        result = _convert(
            {
                "user_id": "u1",
                "total_value": Decimal("100"),
                "positions": [{"avg_cost": Decimal("50"), "is_active": True}],
                "count": 5,
            }
        )
        assert result == {
            "userId": "u1",
            "totalValue": "100",
            "positions": [{"avgCost": "50", "isActive": True}],
            "count": 5,
        }

    def test_none_passthrough(self):
        assert _convert(None) is None

    def test_primitive_passthrough(self):
        assert _convert(42) == 42
        assert _convert("hello") == "hello"
        assert _convert(True) is True


class TestCamelJSONResponse:
    def test_renders_camel_case(self):
        response = CamelJSONResponse(content={"user_id": "123", "total_value": Decimal("100")})
        body = json.loads(response.body)
        assert body == {"userId": "123", "totalValue": "100"}

    def test_renders_empty_dict(self):
        response = CamelJSONResponse(content={})
        body = json.loads(response.body)
        assert body == {}
