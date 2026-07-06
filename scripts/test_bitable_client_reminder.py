"""bitable_client reminder 表操作测试 —— mock HTTP，不真实请求飞书"""

import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# Must set env early before app import
os.environ["MEMBER_MAP_JSON"] = '{"ou_u1":"Alice"}'
import importlib
import app.config
import app.bitable_client
import app.feishu_client
import app.time_utils

importlib.reload(app.config)
importlib.reload(app.feishu_client)
importlib.reload(app.bitable_client)
importlib.reload(app.time_utils)

from app.bitable_client import bitable_client


@pytest.fixture(autouse=True)
def reset_singletons():
    bitable_client._app_token = "fake_app_token"
    bitable_client._table_reminder_records = "fake_reminder_table"
    yield
    bitable_client._app_token = app.config.settings.feishu_bitable_app_token
    bitable_client._table_reminder_records = app.config.settings.feishu_table_reminder_records


@pytest.mark.asyncio
async def test_append_reminder_record_fields():
    """写入时字段完整且默认 status=pending"""
    mock_headers = {"Authorization": "Bearer fake"}
    with patch.object(bitable_client, "_get_headers", AsyncMock(return_value=mock_headers)):
        with patch.object(bitable_client, "_client") as mock_http:
            mock_http.post = AsyncMock(return_value=MagicMock(
                json=lambda: {"code": 0, "data": {"record": {"record_id": "rec_xxx"}}}
            ))

            result = await bitable_client.append_reminder_record(
                raw_text="下周三 shuyao 去杭州",
                creator="Alice",
                scope="member",
                target_person="shuyao",
                event_text="去杭州",
                event_date="2026-07-08",
                remind_at=1780992000,
                remind_text="今天 shuyao 去杭州",
                chat_id="oc_fake_chat",
            )
            assert result is not None
            assert result.get("code") == 0

            # Verify the request payload
            call_args = mock_http.post.call_args
            assert call_args is not None
            url = call_args[0][0]
            assert "reminder" in url.lower() or "fake_reminder_table" in url

            payload = call_args[1].get("json", {})
            fields = payload.get("fields", {})
            assert fields["raw_text"] == "下周三 shuyao 去杭州"
            assert fields["creator"] == "Alice"
            assert fields["scope"] == "member"
            assert fields["target_person"] == "shuyao"
            assert fields["event_text"] == "去杭州"
            assert fields["chat_id"] == "oc_fake_chat"
            assert fields["status"] == "pending"
            assert "sent_at" not in fields, "sent_at should NOT be set for new reminders"


@pytest.mark.asyncio
async def test_find_pending_reminders_query():
    """pending 提醒查询字段完整"""
    mock_headers = {"Authorization": "Bearer fake"}
    fake_items = [
        {
            "record_id": "rec_001",
            "fields": {
                "remind_text": "今天 shuyao 去杭州",
                "chat_id": "oc_chat",
                "remind_at": 1780992000000,
                "status": "pending",
            },
        }
    ]

    with patch.object(bitable_client, "_get_headers", AsyncMock(return_value=mock_headers)):
        with patch.object(bitable_client, "_client") as mock_http:
            mock_http.post = AsyncMock(return_value=MagicMock(
                json=lambda: {"code": 0, "data": {"items": fake_items}}
            ))

            items = await bitable_client.find_pending_reminders(now_ts_ms=1780992000000)
            assert len(items) == 1
            assert items[0]["record_id"] == "rec_001"

            # Verify filter conditions
            call_args = mock_http.post.call_args
            payload = call_args[1].get("json", {})
            conditions = payload["filter"]["conditions"]
            field_names = {c["field_name"] for c in conditions}
            assert "status" in field_names
            assert "remind_at" in field_names


@pytest.mark.asyncio
async def test_find_pending_reminders_empty():
    """没有到期提醒时返回空列表"""
    mock_headers = {"Authorization": "Bearer fake"}
    with patch.object(bitable_client, "_get_headers", AsyncMock(return_value=mock_headers)):
        with patch.object(bitable_client, "_client") as mock_http:
            mock_http.post = AsyncMock(return_value=MagicMock(
                json=lambda: {"code": 0, "data": {"items": []}}
            ))

            items = await bitable_client.find_pending_reminders(now_ts_ms=0)
            assert items == []


@pytest.mark.asyncio
async def test_update_reminder_status():
    """更新状态和 sent_at"""
    mock_headers = {"Authorization": "Bearer fake"}
    with patch.object(bitable_client, "_get_headers", AsyncMock(return_value=mock_headers)):
        with patch.object(bitable_client, "_client") as mock_http:
            mock_http.put = AsyncMock(return_value=MagicMock(
                json=lambda: {"code": 0, "data": {}}
            ))

            ok = await bitable_client.update_reminder_status("rec_001", "sent", 1780992000)
            assert ok is True

            call_args = mock_http.put.call_args
            payload = call_args[1].get("json", {})
            fields = payload.get("fields", {})
            assert fields["status"] == "sent"
            assert fields["sent_at"] == 1780992000000  # ms conversion


@pytest.mark.asyncio
async def test_update_reminder_status_failed():
    """失败场景可更新为 failed"""
    mock_headers = {"Authorization": "Bearer fake"}
    with patch.object(bitable_client, "_get_headers", AsyncMock(return_value=mock_headers)):
        with patch.object(bitable_client, "_client") as mock_http:
            mock_http.put = AsyncMock(return_value=MagicMock(
                json=lambda: {"code": 0, "data": {}}
            ))

            ok = await bitable_client.update_reminder_status("rec_001", "failed", 1780992000)
            assert ok is True

            call_args = mock_http.put.call_args
            payload = call_args[1].get("json", {})
            assert payload["fields"]["status"] == "failed"


@pytest.mark.asyncio
async def test_append_reminder_not_configured():
    """位表未配置时调用不抛异常"""
    with patch.object(bitable_client, "_app_token", ""):
        result = await bitable_client.append_reminder_record(
            raw_text="test", creator="A", scope="family",
            target_person="", event_text="test", event_date="2026-07-08",
            remind_at=0, remind_text="test", chat_id="oc_c",
        )
        assert result is None


@pytest.mark.asyncio
async def test_find_pending_not_configured():
    with patch.object(bitable_client, "_app_token", ""):
        items = await bitable_client.find_pending_reminders(0)
        assert items == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
