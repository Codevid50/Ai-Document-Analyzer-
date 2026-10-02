import json
import pytest

from app.ai_service import (
    clean_json_response,
    parse_json_response,
    valid_string_list,
    validate_summary_text,
    validate_chunk_summary,
    validate_final_summary,
    AIMalformedResponseError,
    AINonJsonResponseError,
)


class TestCleanJsonResponse:

    def test_plain_json(self):
        raw = '{"key": "value"}'
        assert clean_json_response(raw) == '{"key": "value"}'

    def test_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        assert clean_json_response(raw) == '{"key": "value"}'

    def test_markdown_json_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        assert clean_json_response(raw) == '{"key": "value"}'

    def test_markdown_generic_fence(self):
        raw = '```\n{"key": "value"}\n```'
        assert clean_json_response(raw) == '{"key": "value"}'

    def test_empty_string(self):
        assert clean_json_response("") == ""

    def test_whitespace_only(self):
        assert clean_json_response("   \n  ") == ""


class TestParseJsonResponse:

    def test_valid_json(self):
        raw = '{"summary": "test", "key_points": ["a"]}'
        result = parse_json_response(raw)
        assert result["summary"] == "test"
        assert result["key_points"] == ["a"]

    def test_json_with_code_fence(self):
        raw = '```json\n{"summary": "test"}\n```'
        result = parse_json_response(raw)
        assert result["summary"] == "test"

    def test_json_with_whitespace(self):
        raw = '  \n  {"summary": "test"}  \n  '
        result = parse_json_response(raw)
        assert result["summary"] == "test"

    def test_empty_string_raises(self):
        with pytest.raises(AIMalformedResponseError):
            parse_json_response("")

    def test_invalid_json_raises(self):
        with pytest.raises(AINonJsonResponseError):
            parse_json_response("not json at all")

    def test_non_json_safety_response_raises(self):
        with pytest.raises(AINonJsonResponseError):
            parse_json_response("User Safety: safe")

    def test_non_json_plain_text_raises(self):
        with pytest.raises(AINonJsonResponseError):
            parse_json_response("This is a plain text response from the model.")

    def test_non_json_html_raises(self):
        with pytest.raises(AINonJsonResponseError):
            parse_json_response("<html><body>Hello</body></html>")

    def test_json_string_raises(self):
        # A JSON string is valid JSON but not a dict
        with pytest.raises(AIMalformedResponseError):
            parse_json_response('"hello"')

    def test_non_object_json_raises(self):
        with pytest.raises(AIMalformedResponseError):
            parse_json_response('["not", "an", "object"]')

    def test_array_json_raises(self):
        with pytest.raises(AIMalformedResponseError):
            parse_json_response("[1, 2, 3]")

    def test_string_json_raises(self):
        with pytest.raises(AIMalformedResponseError):
            parse_json_response('"just a string"')


class TestValidateSummaryText:

    def test_valid_string(self):
        assert validate_summary_text("hello") is True

    def test_string_with_whitespace(self):
        assert validate_summary_text("  hello  ") is True

    def test_empty_string(self):
        assert validate_summary_text("") is False

    def test_whitespace_only(self):
        assert validate_summary_text("   ") is False

    def test_none(self):
        assert validate_summary_text(None) is False

    def test_integer(self):
        assert validate_summary_text(123) is False

    def test_list(self):
        assert validate_summary_text(["a"]) is False


class TestValidStringList:

    def test_valid_list(self):
        assert valid_string_list(["a", "b", "c"], minimum=2, maximum=5) is True

    def test_exact_minimum(self):
        assert valid_string_list(["a", "b"], minimum=2) is True

    def test_below_minimum(self):
        assert valid_string_list(["a"], minimum=2) is False

    def test_above_maximum(self):
        assert valid_string_list(["a", "b", "c"], minimum=1, maximum=2) is False

    def test_no_maximum(self):
        items = [f"item_{i}" for i in range(20)]
        assert valid_string_list(items, minimum=5) is True

    def test_empty_list(self):
        assert valid_string_list([], minimum=1) is False

    def test_non_list(self):
        assert valid_string_list("not a list", minimum=1) is False

    def test_list_with_empty_string(self):
        assert valid_string_list(["a", "", "c"], minimum=2) is False

    def test_list_with_non_string(self):
        assert valid_string_list(["a", 123, "c"], minimum=2) is False

    def test_list_with_whitespace_only(self):
        assert valid_string_list(["a", "  ", "c"], minimum=2) is False

    def test_none(self):
        assert valid_string_list(None, minimum=1) is False


class TestValidateChunkSummary:

    def test_valid(self):
        data = {
            "summary": "A good summary.",
            "key_points": ["Point 1", "Point 2", "Point 3"],
        }
        assert validate_chunk_summary(data) is True

    def test_valid_5_points(self):
        data = {
            "summary": "A good summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
        }
        assert validate_chunk_summary(data) is True

    def test_missing_summary(self):
        data = {
            "key_points": ["P1", "P2", "P3"],
        }
        assert validate_chunk_summary(data) is False

    def test_empty_summary(self):
        data = {
            "summary": "  ",
            "key_points": ["P1", "P2", "P3"],
        }
        assert validate_chunk_summary(data) is False

    def test_too_few_points(self):
        data = {
            "summary": "A summary.",
            "key_points": ["P1", "P2"],
        }
        assert validate_chunk_summary(data) is False

    def test_too_many_points(self):
        data = {
            "summary": "A summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5", "P6"],
        }
        assert validate_chunk_summary(data) is False

    def test_missing_key_points(self):
        data = {
            "summary": "A summary.",
        }
        assert validate_chunk_summary(data) is False

    def test_empty_key_points(self):
        data = {
            "summary": "A summary.",
            "key_points": [],
        }
        assert validate_chunk_summary(data) is False

    def test_summary_wrong_type(self):
        data = {
            "summary": 123,
            "key_points": ["P1", "P2", "P3"],
        }
        assert validate_chunk_summary(data) is False


class TestValidateFinalSummary:

    def test_valid(self):
        data = {
            "summary": "A comprehensive summary of the document.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": ["T1", "T2", "T3"],
        }
        assert validate_final_summary(data) is True

    def test_valid_8_points(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
            "key_takeaways": ["T1", "T2", "T3", "T4", "T5"],
        }
        assert validate_final_summary(data) is True

    def test_missing_summary(self):
        data = {
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": ["T1", "T2", "T3"],
        }
        assert validate_final_summary(data) is False

    def test_empty_summary(self):
        data = {
            "summary": "   ",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": ["T1", "T2", "T3"],
        }
        assert validate_final_summary(data) is False

    def test_too_few_points(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4"],
            "key_takeaways": ["T1", "T2", "T3"],
        }
        assert validate_final_summary(data) is False

    def test_too_many_points(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"],
            "key_takeaways": ["T1", "T2", "T3"],
        }
        assert validate_final_summary(data) is False

    def test_too_few_takeaways(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": ["T1", "T2"],
        }
        assert validate_final_summary(data) is False

    def test_too_many_takeaways(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": ["T1", "T2", "T3", "T4", "T5", "T6"],
        }
        assert validate_final_summary(data) is False

    def test_missing_takeaways(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
        }
        assert validate_final_summary(data) is False

    def test_empty_takeaways(self):
        data = {
            "summary": "Summary.",
            "key_points": ["P1", "P2", "P3", "P4", "P5"],
            "key_takeaways": [],
        }
        assert validate_final_summary(data) is False

    def test_empty_dict(self):
        assert validate_final_summary({}) is False
