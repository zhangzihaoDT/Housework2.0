"""llm_parser 提醒解析回归测试 —— mock LLM，不真实调用"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.llm_parser import LLMParser
from app.schemas import ReminderParsedResult


@pytest.fixture
def parser():
    """返回一个 LLMParser 实例，不依赖真实 API key 或网络"""
    p = LLMParser()
    # Mark it as configured so parse_reminder_text skips the early return
    p._api_key = "test-key"
    return p


def make_fake_response(content: str) -> dict:
    """模拟 LLM API 返回体"""
    return {
        "choices": [{"message": {"content": content}}]
    }


@pytest.mark.asyncio
async def test_parse_valid_reminder(parser):
    """合法 JSON，is_reminder=true → 得到 ReminderParsedResult"""
    llm_json = """{"is_reminder":true,"target_person":"shuyao","event_text":"去杭州","event_date":"2026-07-08","remind_time":"08:00","remind_text":"今天 shuyao 去杭州"}"""
    result = parser._parse_reminder_response(llm_json)
    assert isinstance(result, ReminderParsedResult)
    assert result.is_reminder is True
    assert result.target_person == "shuyao"
    assert result.event_text == "去杭州"
    assert result.event_date == "2026-07-08"
    assert result.remind_time == "08:00"
    assert result.remind_text == "今天 shuyao 去杭州"


@pytest.mark.asyncio
async def test_parse_non_reminder(parser):
    """is_reminder=false → 不写入提醒"""
    llm_json = '{"is_reminder":false,"event_text":"","event_date":"","remind_time":"","remind_text":""}'
    result = parser._parse_reminder_response(llm_json)
    assert isinstance(result, ReminderParsedResult)
    assert result.is_reminder is False


@pytest.mark.asyncio
async def test_parse_malformed_json(parser):
    """malformed JSON → 安全降级，不抛异常"""
    result = parser._parse_reminder_response("这不是 JSON")
    assert isinstance(result, ReminderParsedResult)
    assert result.is_reminder is False


@pytest.mark.asyncio
async def test_parse_empty_response(parser):
    """空响应 → 安全降级"""
    result = parser._parse_reminder_response("")
    assert isinstance(result, ReminderParsedResult)
    assert result.is_reminder is False


@pytest.mark.asyncio
async def test_parse_partial_fields(parser):
    """部分字段缺失 → 使用默认值，不抛异常"""
    llm_json = '{"is_reminder":true}'
    result = parser._parse_reminder_response(llm_json)
    assert result.is_reminder is True
    assert result.target_person == ""
    assert result.event_text == ""
    assert result.event_date == ""
    assert result.remind_time == ""
    assert result.remind_text == ""


@pytest.mark.asyncio
async def test_parse_markdown_fence(parser):
    """LLM 返回 markdown 代码块 → 正确提取 JSON"""
    llm_response = """```json
{"is_reminder":true,"target_person":"妈妈","event_text":"体检","event_date":"2026-08-05","remind_time":"08:00","remind_text":"今天 妈妈 体检"}
```"""
    result = parser._parse_reminder_response(llm_response)
    assert result.is_reminder is True
    assert result.target_person == "妈妈"
    assert result.event_text == "体检"


@pytest.mark.asyncio
async def test_parse_not_a_dict(parser):
    """LLM 返回非 dict JSON → 安全降级"""
    result = parser._parse_reminder_response('["not", "a", "dict"]')
    assert isinstance(result, ReminderParsedResult)
    assert result.is_reminder is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
