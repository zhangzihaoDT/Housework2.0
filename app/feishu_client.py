"""飞书开放平台 API 客户端（凭证、发送消息等）"""

import json
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_EXPIRE_BUFFER = 120


class FeishuClient:
    def __init__(self) -> None:
        self._app_id = settings.feishu_app_id
        self._app_secret = settings.feishu_app_secret
        self._base_url = "https://open.feishu.cn/open-apis"
        self._client = httpx.AsyncClient(base_url=self._base_url)

        self._tenant_token: str = ""
        self._token_expires_at: float = 0.0

    async def get_tenant_access_token(self) -> str:
        if self._tenant_token and time.time() < self._token_expires_at:
            return self._tenant_token

        logger.info("fetching new tenant_access_token ...")
        resp = await self._client.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        data = resp.json()

        if data.get("code") != 0:
            logger.error(
                "failed to get tenant_access_token: code=%s msg=%s",
                data.get("code"),
                data.get("msg"),
            )
            return self._tenant_token

        self._tenant_token = data["tenant_access_token"]
        expire_seconds = data.get("expire", 7200)
        self._token_expires_at = time.time() + expire_seconds - TOKEN_EXPIRE_BUFFER
        logger.info("tenant_access_token acquired, expires in %ds", expire_seconds)
        return self._tenant_token

    async def send_text_message(
        self, receive_id_type: str, receive_id: str, text: str
    ) -> dict:
        token = await self.get_tenant_access_token()
        if not token:
            logger.error("cannot send message: no valid tenant_access_token")
            return {}

        content = json.dumps({"text": text})
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content,
        }

        resp = await self._client.post(
            f"/im/v1/messages?receive_id_type={receive_id_type}",
            headers=headers,
            json=payload,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(
                "send message failed: code=%s msg=%s data=%s",
                result.get("code"),
                result.get("msg"),
                result.get("data"),
            )
        else:
            logger.info("message sent successfully: message_id=%s", result.get("data", {}).get("message_id"))
        return result


feishu_client = FeishuClient()
