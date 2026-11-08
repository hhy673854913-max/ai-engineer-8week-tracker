import json

import pytest
from pydantic import BaseModel, Field, ValidationError

from code.shared.structured import extract_json, loads_lenient, model_from_text


class Demo(BaseModel):
    title: str = Field(min_length=2)
    score: int


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_from_fence():
    raw = '```json\n{"a": 1}\n```'
    assert loads_lenient(extract_json(raw)) == {"a": 1}


def test_extract_from_explanation():
    raw = '好的，结果如下：{"a": 1} 希望有帮助。'
    assert loads_lenient(extract_json(raw)) == {"a": 1}


def test_trailing_comma_tolerated():
    assert loads_lenient('{"a": 1,}') == {"a": 1}


def test_missing_braces_raises():
    with pytest.raises(ValueError):
        extract_json("没有 json 的对象")


def test_model_from_text_ok():
    model = model_from_text('{"title": "活动", "score": 90}', Demo)
    assert model.score == 90


def test_model_from_text_validation_error():
    with pytest.raises(ValidationError):
        model_from_text('{"title": "x", "score": "high"}', Demo)


def test_json_roundtrip_with_chinese():
    payload = {"title": "春节活动", "score": 88}
    assert loads_lenient(json.dumps(payload, ensure_ascii=False)) == payload
