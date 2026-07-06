"""reminder_scheduler 回归测试 —— mock bitable / feishu，不真实调用"""

import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Set env early
os.environ["MEMBER_MAP_JSON"] = '{}'
import importlib
import app.config
import app.reminder_scheduler
import app.bitable_client
import app.feishu_client

for mod in (app.config, app.feishu_client, app.bitable_client, app.reminder_scheduler):
    importlib.reload(mod)

from app.reminder_scheduler import check_and_send_reminders


def make_reminder_item(record_id: str, remind_text: str, chat_id: str,
                       remind_at_ts: int, status: str = "pending") -> dict:
    return {
        "record_id": record_id,
        "fields": {
            "remind_text": remind_text,
            "chat_id": chat_id,
            "remind_at": remind_at_ts,
            "status": status,
        },
    }


@pytest.mark.asyncio
async def test_no_due_reminders_sends_nothing():
    """没有到期提醒 → 不发送任何消息"""
    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        mock_bitable.find_pending_reminders = AsyncMock(return_value=[])
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        mock_feishu.send_text_message.assert_not_called()
        mock_bitable.update_reminder_status.assert_not_called()
        print("  ✅ 无到期提醒不发送")


@pytest.mark.asyncio
async def test_single_due_reminder_sent():
    """一条到期提醒 → 发送消息 + 更新 status=sent + sent_at"""
    items = [make_reminder_item("rec_001", "今天 shuyao 去杭州", "oc_chat_1", 1780992000000)]

    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        mock_bitable.find_pending_reminders = AsyncMock(return_value=items)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        # Sent to correct chat with correct text
        mock_feishu.send_text_message.assert_awaited_once_with("chat_id", "oc_chat_1", "今天 shuyao 去杭州")
        # Status updated to sent
        mock_bitable.update_reminder_status.assert_awaited_once()
        args = mock_bitable.update_reminder_status.call_args[0]
        assert args[0] == "rec_001"
        assert args[1] == "sent"
        print("  ✅ 到期提醒已发送并更新状态")


@pytest.mark.asyncio
async def test_not_due_reminder_not_sent():
    """未到期的 reminder（remind_at > now）不应发送"""
    # remind_at is in the far future, now_ts_ms is 0
    items = [make_reminder_item("rec_002", "今天全家去迪士尼", "oc_chat_2", 9999999999999)]

    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        # find_pending_reminders already filters by remind_at <= now,
        # so if properly called with a future ts, it should return empty
        mock_bitable.find_pending_reminders = AsyncMock(return_value=[])
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        mock_feishu.send_text_message.assert_not_called()
        print("  ✅ 未到期提醒不发送")


@pytest.mark.asyncio
async def test_sent_reminder_not_resent():
    """已经 sent 的 reminder 不应再次发送 — find_pending_reminders 靠 status filter 排除"""
    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        # Simulate that the query correctly excluded sent records
        mock_bitable.find_pending_reminders = AsyncMock(return_value=[])
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})

        await check_and_send_reminders()

        mock_feishu.send_text_message.assert_not_called()
        print("  ✅ sent 记录不重复发送")


@pytest.mark.asyncio
async def test_send_failure_marks_failed():
    """发送失败 → 标记为 failed，不导致 scheduler 整体崩溃"""
    items = [make_reminder_item("rec_fail", "今天提醒", "oc_fail", 1780992000000)]

    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        mock_bitable.find_pending_reminders = AsyncMock(return_value=items)
        # Simulate send failure
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 999999, "msg": "error"})
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        # Status updated to failed
        args = mock_bitable.update_reminder_status.call_args[0]
        assert args[1] == "failed"
        print("  ✅ 发送失败标记为 failed，scheduler 未崩溃")


@pytest.mark.asyncio
async def test_multiple_due_reminders_all_processed():
    """多条到期提醒逐条处理，单条失败不影响其他"""
    items = [
        make_reminder_item("rec_ok_1", "提醒 A", "oc_a", 1780992000000),
        make_reminder_item("rec_fail", "提醒 B", "oc_b", 1780992000000),
        make_reminder_item("rec_ok_2", "提醒 C", "oc_c", 1780992000000),
    ]

    send_call_count = 0

    async def send_side_effect(*args, **kwargs):
        nonlocal send_call_count
        send_call_count += 1
        if send_call_count == 2:
            return {"code": 999999}  # second one fails
        return {"code": 0}

    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        mock_bitable.find_pending_reminders = AsyncMock(return_value=items)
        mock_feishu.send_text_message = AsyncMock(side_effect=send_side_effect)
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        # All three should be sent
        assert mock_feishu.send_text_message.await_count == 3
        # All three should have status update
        assert mock_bitable.update_reminder_status.await_count == 3

        # Check status values
        calls = mock_bitable.update_reminder_status.call_args_list
        assert calls[0].args[1] == "sent"   # rec_ok_1
        assert calls[1].args[1] == "failed" # rec_fail
        assert calls[2].args[1] == "sent"   # rec_ok_2
        print("  ✅ 多条提醒逐条处理，单条失败不影响其他")


@pytest.mark.asyncio
async def test_incomplete_record_skipped():
    """字段不完整的记录跳过，不抛异常"""
    items = [
        {"record_id": "rec_incomplete", "fields": {}},  # missing remind_text & chat_id
        make_reminder_item("rec_ok", "有效提醒", "oc_ok", 1780992000000),
    ]

    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = True
        mock_bitable.find_pending_reminders = AsyncMock(return_value=items)
        mock_feishu.send_text_message = AsyncMock(return_value={"code": 0})
        mock_bitable.update_reminder_status = AsyncMock(return_value=True)

        await check_and_send_reminders()

        # Only the valid one should be sent
        mock_feishu.send_text_message.assert_awaited_once()
        mock_bitable.update_reminder_status.assert_awaited_once()
        print("  ✅ 不完整记录跳过，不崩溃")


@pytest.mark.asyncio
async def test_not_configured_returns_early():
    """未配置位表时直接返回"""
    with patch("app.reminder_scheduler.bitable_client") as mock_bitable, \
         patch("app.reminder_scheduler.feishu_client") as mock_feishu:

        mock_bitable.is_configured = False

        await check_and_send_reminders()

        mock_bitable.find_pending_reminders.assert_not_called()
        mock_feishu.send_text_message.assert_not_called()
        print("  ✅ 未配置时不执行任何操作")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
