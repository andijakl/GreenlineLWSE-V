"""Test Greenline entity helpers."""

import pytest

from custom_components.greenline_lwse_v.entity import parse_temperature


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, None, id="missing"),
        pytest.param("---", None, id="unavailable"),
        pytest.param("not-a-number", None, id="malformed"),
        pytest.param("nan", None, id="not-a-number"),
        pytest.param("inf", None, id="infinite"),
        pytest.param("21.5", 21.5, id="valid"),
    ],
)
def test_parse_temperature(value: str | None, expected: float | None) -> None:
    """Test parsing valid and malformed device temperature values."""
    assert parse_temperature(value) == expected
