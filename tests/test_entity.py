"""Test Greenline entity helpers."""

import pytest

from custom_components.greenline_lwse_v.entity import parse_number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, None, id="missing"),
        pytest.param("---", None, id="unavailable"),
        pytest.param("not-a-number", None, id="malformed"),
        pytest.param("nan", None, id="not-a-number"),
        pytest.param("inf", None, id="infinite"),
        pytest.param("21.5", 21.5, id="decimal"),
        pytest.param("96508", 96508, id="whole-number"),
    ],
)
def test_parse_number(value: str | None, expected: float | None) -> None:
    """Test parsing valid and malformed device values."""
    result = parse_number(value)
    assert result == expected
    assert type(result) is type(expected)
