"""event_handler 消息分流回归测试 —— mock 飞书 / LLM，不真实调用"""

import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock, ANY

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Set env early
os.environ["MEMBER_MAP_JSON"] = '{"ou_sender":"Zihao"}'
import importlib
import app.config
import app.event_handler
import app.bitable_client
import app.feishu_client
import app.llm_parser
import app.chore_service
import app.reminder_service

for mod in (app.config, app.feishu_client, app.bitable_client, app.llm_parser,
            app.chore_service, app.reminder_service, app.event_handler):
    importlib.reload(mod)

# Re-import after reload
from app.event_handler import handle_chore_message
from app.schemas import ParsedIncomingMessage, ReminderParsedResult, LLMParseResult, ParsedChoreTask
from app.chore_service import normalize_chore_input_text, extract_chore_text


def make_msg(raw_text: str, mid: str = "msg_test", cid: str = "oc_test") -> ParsedIncomingMessage:
    return ParsedIncomingMessage(
        message_id=mid,
        chat_id=cid,
        sender_open_id="ou_sender",
        raw_text=raw_text,
        receive_id_type="chat_id",
        receive_id=cid,
    )


@pytest.fixture(autouse=True)
def reset_dedup():
    """Clear dedup set between tests"""
    app.event_handler._processed_message_ids.clear()
    yield


@pytest.mark.asyncio
async def test_reminder_message_routes_to_reminder():
    """提醒文本 → 走 reminder 流程，调用 append_reminder_record，不调用 append_raw_input"""
    msg = make_msg("@小哈皮 下周三 shuyao 去杭州", mid="routing_001")

    mock_reminder_result = ReminderParsedResult(
        is_reminder=True,
        target_person="shuyao",
        event_text="去杭州",
        event_date="2026-07-08",
        remind_time="08:00",
        remind_text="今天 shuyao 去杭州",
    )

    with patch("app.event_handler.bitable_client") as mock_bitable, \
         patch("app.event_handler.feishu_client") as mock_feishu, \
         patch("app.event_handler.llm_parser") as mock_llm, \
         patch("app.event_handler.matches_reminder_pattern", return_value=True), \
         patch("app.event_handler.get_today_info", return_value=("2026-07-06", "一")):

        mock_bitable.is_configured = True
        mock_bitable.find_raw_input_by_message_id = AsyncMock(return_value=False)
        mock_bitable.append_reminder_record = AsyncMock(return_value={"code": 0})
        mock_llm.parse_reminder_text = AsyncMock(return_value=mock_reminder_result)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})

        reply = await handle_chore_message(msg)

        # Should have called reminder parser
        mock_llm.parse_reminder_text.assert_awaited_once()
        # Should have written to reminder table
        mock_bitable.append_reminder_record.assert_awaited_once()
        # Should NOT have written to raw_inputs (chore path)
        mock_bitable.append_raw_input.assert_not_called()
        # Reply mentions reminder
        assert reply is not None
        assert "已记录提醒" in reply
        assert "08:00" in reply


@pytest.mark.asyncio
async def test_chore_message_still_goes_to_chore():
    """普通家务文本 → 不走 reminder 流，继续原家务积分流程"""
    msg = make_msg("@小哈皮 我洗碗了", mid="routing_002")

    mock_chore_result = LLMParseResult(
        tasks=[ParsedChoreTask(task_type="洗碗", confidence=0.98, evidence="我洗碗了")],
        ignored=[],
        need_confirm=False,
    )

    with patch("app.event_handler.bitable_client") as mock_bitable, \
         patch("app.event_handler.feishu_client") as mock_feishu, \
         patch("app.event_handler.llm_parser") as mock_llm:

        mock_bitable.is_configured = True
        mock_bitable.find_raw_input_by_message_id = AsyncMock(return_value=False)
        mock_bitable.append_raw_input = AsyncMock(return_value={"code": 0})
        mock_bitable.append_chore_records = AsyncMock(return_value=[{"code": 0}])
        mock_llm.parse_chore_text = AsyncMock(return_value=mock_chore_result)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})

        reply = await handle_chore_message(msg)

        # Should have called chore parser, not reminder parser
        mock_llm.parse_chore_text.assert_awaited_once()
        mock_llm.parse_reminder_text.assert_not_called()
        # Should have written to chore tables
        mock_bitable.append_raw_input.assert_awaited_once()
        mock_bitable.append_chore_records.assert_awaited_once()
        # Reply mentions chores
        assert reply is not None
        assert "已记录" in reply
        assert "洗碗" in reply


@pytest.mark.asyncio
async def test_pseudo_reminder_rejected_by_llm_falls_back():
    """含日期关键词但 LLM 判定非提醒 → 回退原家务流程"""
    msg = make_msg("@小哈皮 明天我洗碗了", mid="routing_003")

    mock_reminder_result = ReminderParsedResult(
        is_reminder=False,
        target_person="",
        event_text="",
        event_date="",
        remind_time="",
        remind_text="",
    )
    mock_chore_result = LLMParseResult(
        tasks=[ParsedChoreTask(task_type="洗碗", confidence=0.95, evidence="洗碗了")],
        ignored=[],
        need_confirm=False,
    )

    with patch("app.event_handler.bitable_client") as mock_bitable, \
         patch("app.event_handler.feishu_client") as mock_feishu, \
         patch("app.event_handler.llm_parser") as mock_llm, \
         patch("app.event_handler.matches_reminder_pattern", return_value=True), \
         patch("app.event_handler.get_today_info", return_value=("2026-07-06", "一")):

        mock_bitable.is_configured = True
        mock_bitable.find_raw_input_by_message_id = AsyncMock(return_value=False)
        mock_bitable.append_raw_input = AsyncMock(return_value={"code": 0})
        mock_bitable.append_chore_records = AsyncMock(return_value=[{"code": 0}])
        mock_llm.parse_reminder_text = AsyncMock(return_value=mock_reminder_result)
        mock_llm.parse_chore_text = AsyncMock(return_value=mock_chore_result)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})

        reply = await handle_chore_message(msg)

        # Reminder parser was called but rejected
        mock_llm.parse_reminder_text.assert_awaited_once()
        # Chore parser was called as fallback
        mock_llm.parse_chore_text.assert_awaited_once()
        # Should NOT have written to reminder table
        mock_bitable.append_reminder_record.assert_not_called()
        # Reply mentions chores
        assert reply is not None
        assert "已记录" in reply


@pytest.mark.asyncio
async def test_chore_message_no_date_keyword_bypasses_reminder():
    """纯家务文本无日期关键词 → 直接走 chores，不触发 reminder 预检"""
    msg = make_msg("@小哈皮 我拖地了", mid="routing_004")

    mock_chore_result = LLMParseResult(
        tasks=[ParsedChoreTask(task_type="拖地", confidence=0.98, evidence="拖地了")],
        ignored=[],
        need_confirm=False,
    )

    with patch("app.event_handler.bitable_client") as mock_bitable, \
         patch("app.event_handler.feishu_client") as mock_feishu, \
         patch("app.event_handler.llm_parser") as mock_llm:

        mock_bitable.is_configured = True
        mock_bitable.find_raw_input_by_message_id = AsyncMock(return_value=False)
        mock_bitable.append_raw_input = AsyncMock(return_value={"code": 0})
        mock_bitable.append_chore_records = AsyncMock(return_value=[{"code": 0}])
        mock_llm.parse_chore_text = AsyncMock(return_value=mock_chore_result)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})

        reply = await handle_chore_message(msg)

        mock_llm.parse_chore_text.assert_awaited_once()
        mock_llm.parse_reminder_text.assert_not_called()
        assert reply is not None
        assert "拖地" in reply


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
