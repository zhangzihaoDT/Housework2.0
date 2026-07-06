"""飞书多维表格 API 客户端"""

import json
import logging

import httpx

from app.config import settings
from app.feishu_client import feishu_client as _feishu_client
from app.time_utils import to_feishu_timestamp_ms, now_local

logger = logging.getLogger(__name__)


class BitableClient:
    def __init__(self) -> None:
        self._app_token = settings.feishu_bitable_app_token
        self._table_raw_inputs = settings.feishu_table_raw_inputs
        self._table_chore_records = settings.feishu_table_chore_records
        self._table_reminder_records = settings.feishu_table_reminder_records
        self._base_url = "https://open.feishu.cn/open-apis"
        self._client = httpx.AsyncClient(base_url=self._base_url)
        self._fields_cache: dict[str, list[str]] = {}
        self._fields_id_cache: dict[str, dict[str, str]] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self._app_token)

    async def _get_headers(self) -> dict[str, str] | None:
        token = await _feishu_client.get_tenant_access_token()
        if not token:
            logger.error("cannot write to bitable: no valid tenant_access_token")
            return None
        return {"Authorization": f"Bearer {token}"}

    async def _append_record(self, table_id: str, fields: dict) -> dict | None:
        if not self._app_token or not table_id:
            return None

        headers = await self._get_headers()
        if not headers:
            return None

        url = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records"

        try:
            resp = await self._client.post(url, headers=headers, json={"fields": fields})
            result = resp.json()
        except httpx.HTTPError as e:
            logger.error("bitable HTTP request failed: url=%s error=%s", url, e)
            raise

        if result.get("code") != 0:
            logger.error(
                "bitable append record failed: url=%s code=%s msg=%s data=%s body=%s",
                url,
                result.get("code"),
                result.get("msg"),
                result.get("data"),
                json.dumps(result, ensure_ascii=False),
            )
        else:
            record_id = result.get("data", {}).get("record", {}).get("record_id", "")
            logger.info("bitable record appended: record_id=%s", record_id)

        return result

    async def list_table_fields(self, table_id: str) -> list[str]:
        if not self._app_token or not table_id:
            return []

        headers = await self._get_headers()
        if not headers:
            return []

        url = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"

        try:
            resp = await self._client.get(url, headers=headers)
            result = resp.json()
        except httpx.HTTPError as e:
            logger.error("list fields HTTP error: url=%s error=%s", url, e)
            return []

        if result.get("code") != 0:
            logger.error(
                "list fields failed: url=%s code=%s msg=%s body=%s",
                url,
                result.get("code"),
                result.get("msg"),
                json.dumps(result, ensure_ascii=False),
            )
            return []

        items = result.get("data", {}).get("items", [])
        field_names = [item["field_name"] for item in items if "field_name" in item]
        logger.info("table fields: table_id=%s fields=%s", table_id, field_names)
        return field_names

    async def _get_table_fields_with_ids_cached(self, table_id: str) -> dict[str, str]:
        if table_id not in self._fields_id_cache:
            self._fields_id_cache[table_id] = await self._list_table_fields_with_ids(table_id)
        return self._fields_id_cache[table_id]

    async def _list_table_fields_with_ids(self, table_id: str) -> dict[str, str]:
        result = {}
        if not self._app_token or not table_id:
            return result

        headers = await self._get_headers()
        if not headers:
            return result

        url = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"

        try:
            resp = await self._client.get(url, headers=headers)
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("list fields HTTP error: url=%s error=%s", url, e)
            return result

        if data.get("code") != 0:
            logger.error(
                "list fields failed: url=%s code=%s msg=%s body=%s",
                url,
                data.get("code"),
                data.get("msg"),
                json.dumps(data, ensure_ascii=False),
            )
            return result

        items = data.get("data", {}).get("items", [])
        for item in items:
            field_name = item.get("field_name", "")
            field_id = item.get("field_id", "")
            if field_name and field_id:
                result[field_name] = field_id
        return result

    async def _get_table_fields_cached(self, table_id: str) -> list[str]:
        if table_id not in self._fields_cache:
            fields = await self.list_table_fields(table_id)
            self._fields_cache[table_id] = fields
        return self._fields_cache[table_id]

    async def validate_required_fields(self) -> dict:
        raw_inputs_required = {
            "message_id", "chat_id", "sender_id", "raw_text",
            "normalized_text", "chore_text", "status", "received_at",
            "ai_result_json", "total_points", "task_count",
            "reply_text", "error_message",
        }
        chore_records_required = {
            "record_id", "message_id", "chat_id", "sender_id",
            "member_name", "task_type", "points", "confidence",
            "evidence", "source_text", "status", "created_at",
            "date", "week", "month",
        }

        raw_fields = await self._get_table_fields_cached(self._table_raw_inputs)
        raw_set = set(raw_fields)
        raw_missing = sorted(raw_inputs_required - raw_set)

        chore_fields = await self._get_table_fields_cached(self._table_chore_records)
        chore_set = set(chore_fields)
        chore_missing = sorted(chore_records_required - chore_set)

        return {
            "raw_inputs": {
                "ok": len(raw_missing) == 0,
                "missing": raw_missing,
                "fields": raw_fields,
            },
            "chore_records": {
                "ok": len(chore_missing) == 0,
                "missing": chore_missing,
                "fields": chore_fields,
            },
        }

    async def find_raw_input_by_message_id(self, message_id: str) -> bool:
        if not self._app_token or not self._table_raw_inputs:
            return False

        name_to_id = await self._get_table_fields_with_ids_cached(self._table_raw_inputs)
        if "message_id" not in name_to_id:
            logger.warning(
                "persistent dedup skipped: field 'message_id' not found in table %s. "
                "Run `python scripts/check_bitable_schema.py` to check schema.",
                self._table_raw_inputs,
            )
            return False

        headers = await self._get_headers()
        if not headers:
            return False

        url = f"/bitable/v1/apps/{self._app_token}/tables/{self._table_raw_inputs}/records/search"

        payload = {
            "field_names": ["message_id"],
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "message_id",
                        "operator": "is",
                        "value": [message_id],
                    }
                ],
            },
            "page_size": 1,
        }

        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            result = resp.json()
            if result.get("code") == 0:
                items = result.get("data", {}).get("items", [])
                if items:
                    logger.info(
                        "persistent dedup: found existing record for message_id=%s",
                        message_id,
                    )
                    return True
                return False
            logger.warning(
                "persistent dedup search failed: code=%s msg=%s body=%s",
                result.get("code"),
                result.get("msg"),
                json.dumps(result, ensure_ascii=False),
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.warning("persistent dedup HTTP error: %s", e)
            return False
        except Exception as e:
            logger.warning("persistent dedup error: %s", e)
            return False

    async def append_raw_input(
        self,
        message_id: str,
        chat_id: str,
        sender_id: str,
        raw_text: str,
        normalized_text: str,
        chore_text: str,
        status: str,
        received_at: int,
        ai_result_json: str | None = None,
        total_points: int | None = None,
        task_count: int | None = None,
        reply_text: str | None = None,
        error_message: str | None = None,
    ) -> dict | None:
        from app.time_utils import to_feishu_timestamp_ms, to_datetime

        fields = {
            "message_id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "raw_text": raw_text,
            "normalized_text": normalized_text,
            "chore_text": chore_text,
            "status": status,
            "received_at": to_feishu_timestamp_ms(to_datetime(received_at)),
        }
        if ai_result_json is not None:
            fields["ai_result_json"] = ai_result_json
        if total_points is not None:
            fields["total_points"] = total_points
        if task_count is not None:
            fields["task_count"] = task_count
        if reply_text is not None:
            fields["reply_text"] = reply_text
        if error_message is not None:
            fields["error_message"] = error_message
        return await self._append_record(self._table_raw_inputs, fields)

    async def append_chore_record(
        self,
        message_id: str,
        chat_id: str,
        sender_id: str,
        task_type: str,
        points: int,
        confidence: float,
        evidence: str,
        source_text: str,
        status: str = "confirmed",
        created_at: int | None = None,
        member_name: str | None = None,
        date: int | None = None,
        week: str | None = None,
        month: str | None = None,
    ) -> dict | None:
        from app.time_utils import to_feishu_timestamp_ms, to_datetime

        fields = {
            "message_id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "task_type": task_type,
            "points": points,
            "confidence": confidence,
            "evidence": evidence,
            "source_text": source_text,
            "status": status,
            "created_at": to_feishu_timestamp_ms(to_datetime(created_at)),
        }
        if member_name is not None:
            fields["member_name"] = member_name
        if date is not None:
            fields["date"] = to_feishu_timestamp_ms(to_datetime(date))
        if week is not None:
            fields["week"] = week
        if month is not None:
            fields["month"] = month
        return await self._append_record(self._table_chore_records, fields)

    async def append_chore_records(
        self,
        message_id: str,
        chat_id: str,
        sender_id: str,
        tasks: list,
        source_text: str,
        status: str = "confirmed",
        member_name: str | None = None,
        date: str | None = None,
        week: str | None = None,
        month: str | None = None,
    ) -> list[dict | None]:
        from app.chore_service import get_task_points

        results = []
        for task in tasks:
            points = get_task_points(task.task_type)
            result = await self.append_chore_record(
                message_id=message_id,
                chat_id=chat_id,
                sender_id=sender_id,
                task_type=task.task_type,
                points=points,
                confidence=task.confidence,
                evidence=task.evidence,
                source_text=source_text,
                status=status,
                member_name=member_name,
                date=date,
                week=week,
                month=month,
            )
            results.append(result)
        return results

    async def append_reminder_record(
        self,
        raw_text: str,
        creator: str,
        scope: str,
        target_person: str,
        event_text: str,
        event_date: str,
        remind_at: int,
        remind_text: str,
        chat_id: str,
    ) -> dict | None:
        from app.time_utils import to_feishu_timestamp_ms, to_datetime

        fields = {
            "raw_text": raw_text,
            "creator": creator,
            "scope": scope,
            "target_person": target_person,
            "event_text": event_text,
            "event_date": to_feishu_timestamp_ms(to_datetime(event_date)),
            "remind_at": remind_at * 1000 if remind_at < 1_000_000_000_000 else remind_at,
            "remind_text": remind_text,
            "chat_id": chat_id,
            "status": "pending",
            "created_at": to_feishu_timestamp_ms(now_local()),
            "sent_at": 0,
        }
        return await self._append_record(self._table_reminder_records, fields)

    async def search_reminders_by_filter(self, field_name: str, operator: str, value: list) -> list[dict]:
        if not self._app_token or not self._table_reminder_records:
            return []

        headers = await self._get_headers()
        if not headers:
            return []

        url = f"/bitable/v1/apps/{self._app_token}/tables/{self._table_reminder_records}/records/search"

        payload: dict = {
            "field_names": ["record_id", "remind_text", "chat_id", "remind_at", "status"],
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": field_name,
                        "operator": operator,
                        "value": value,
                    }
                ],
            },
            "page_size": 50,
        }

        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            result = resp.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("items", [])
            logger.warning(
                "search reminders failed: code=%s msg=%s body=%s",
                result.get("code"),
                result.get("msg"),
                json.dumps(result, ensure_ascii=False),
            )
            return []
        except httpx.HTTPError as e:
            logger.warning("search reminders HTTP error: %s", e)
            return []

    async def find_pending_reminders(self, now_ts_ms: int) -> list[dict]:
        if not self._app_token or not self._table_reminder_records:
            return []

        headers = await self._get_headers()
        if not headers:
            return []

        url = f"/bitable/v1/apps/{self._app_token}/tables/{self._table_reminder_records}/records/search"

        payload = {
            "field_names": ["record_id", "remind_text", "chat_id", "remind_at", "status"],
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "status",
                        "operator": "is",
                        "value": ["pending"],
                    },
                    {
                        "field_name": "remind_at",
                        "operator": "less_than_or_equal_to",
                        "value": [now_ts_ms],
                    },
                ],
            },
            "page_size": 50,
        }

        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            result = resp.json()
            if result.get("code") == 0:
                items = result.get("data", {}).get("items", [])
                logger.info("found %d pending reminder(s) to send", len(items))
                return items
            logger.warning(
                "find pending reminders failed: code=%s msg=%s body=%s",
                result.get("code"),
                result.get("msg"),
                json.dumps(result, ensure_ascii=False),
            )
            return []
        except httpx.HTTPError as e:
            logger.warning("find pending reminders HTTP error: %s", e)
            return []

    async def update_reminder_status(
        self, record_id: str, status: str, sent_at: int
    ) -> bool:
        if not self._app_token or not self._table_reminder_records or not record_id:
            return False

        headers = await self._get_headers()
        if not headers:
            return False

        url = (
            f"/bitable/v1/apps/{self._app_token}/tables"
            f"/{self._table_reminder_records}/records/{record_id}"
        )

        payload = {
            "fields": {
                "status": status,
                "sent_at": sent_at * 1000 if sent_at < 1_000_000_000_000 else sent_at,
            }
        }

        try:
            resp = await self._client.put(url, headers=headers, json=payload)
            result = resp.json()
            if result.get("code") == 0:
                logger.info("reminder %s updated to %s", record_id, status)
                return True
            logger.warning(
                "update reminder status failed: record_id=%s code=%s msg=%s",
                record_id,
                result.get("code"),
                result.get("msg"),
            )
            return False
        except httpx.HTTPError as e:
            logger.warning("update reminder status HTTP error: %s", e)
            return False


bitable_client = BitableClient()
