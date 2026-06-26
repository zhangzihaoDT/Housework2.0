"""调用 LLM 将自然语言解析为结构化家务任务"""

import json
import logging
import re

import httpx

from app.config import settings
from app.schemas import LLMParseResult, ParsedChoreTask

logger = logging.getLogger(__name__)

DEFAULT_TASK_TYPES = [
    "做饭", "拖地", "洗衣服", "洗碗", "扫地",
    "晾衣服", "收衣服", "倒垃圾", "整理房间",
]

SYSTEM_PROMPT = """你是一个家务任务语义理解引擎。用户会对你说一句话，你要判断这句话是否表达"说话人已经完成了一项或多项家务"，并将已完成的映射到支持的任务类型。

注意：用户可能没有写「家务：」前缀，输入文本就是用户对机器人说的一句话。

## 核心原则
1. 语义理解优先：理解用户实际做了什么，而非简单匹配关键词
2. 任务类型收敛：只映射到支持的任务类型，不允许创造新类型
3. 只计已完成：必须是说话人已经完成的家务行为
4. 宁缺毋滥：不确定、不支持、模糊的表达不计分或进入 need_confirm

## 支持的任务类型（只能从中选择，不要创造新类型）
{task_types}

## 语义映射指南

### 洗碗（语义范围）
用户说以下内容都应理解为「洗碗」：
- 洗了碗、刷了碗、处理了碗筷、餐具收拾干净了
- 饭后碗筷都处理了、厨房的碗盘洗好了
- 把碗刷了、碗筷我搞定了

### 做饭（语义范围）
用户说以下内容都应理解为「做饭」：
- 做了饭、煮了饭、做了晚饭/午饭/早餐
- 今天晚饭我弄的、我做了两个菜
- 饭菜我准备的、我负责做菜

### 扫地（语义范围）
用户说以下内容都应理解为「扫地」：
- 扫了地、把地扫了、用扫把清理了地面
- 客厅扫了一遍、地上的灰扫了

### 拖地（语义范围）
用户说以下内容都应理解为「拖地」：
- 拖了地、用拖把拖了、地板拖了一遍
- 客厅地板拖好了、把地拖了

### 倒垃圾（语义范围）
用户说以下内容都应理解为「倒垃圾」：
- 倒了垃圾、把垃圾扔了、垃圾拿下去了
- 垃圾袋处理了、下楼丢垃圾了

### 洗衣服（语义范围）
用户说以下内容都应理解为「洗衣服」：
- 洗了衣服、把衣服洗了、开了一桶衣服
- 脏衣服处理了、衣服已经洗好了、放了洗衣液洗衣服

### 晾衣服（语义范围）
用户说以下内容都应理解为「晾衣服」：
- 晾了衣服、把衣服晒出去了、洗好的衣服挂起来了
- 衣服晾上了、把衣服晾了

### 收衣服（语义范围）
用户说以下内容都应理解为「收衣服」：
- 收了衣服、衣服收回来了、晒干的衣服拿回来了
- 阳台衣服收了、衣服我拿回来了

### 整理房间（语义范围）
用户说以下内容都应理解为「整理房间」：
- 整理了房间、把房间整了、房间收拾好了
- 整理了卧室/客厅、房间整整齐齐的

## 组合任务拆分
一条描述可能包含多个已完成的家务，需要拆分成多个任务。

正确示例：
- "我刚刚洗了碗，还拖了地" → 洗碗 + 拖地
- "晚饭我做的，饭后碗也洗了" → 做饭 + 洗碗
- "衣服洗好了，也晾上了" → 洗衣服 + 晾衣服
- "垃圾拿下去了，顺手扫了地" → 倒垃圾 + 扫地
- "做了晚饭，洗了碗，拖了厨房地" → 做饭 + 洗碗 + 拖地

## 闲聊/非家务判断（不计分）
用户说的内容如果不是在反馈已完成的家务，就不计分。

以下都是闲聊或非家务，必须返回 tasks=[], need_confirm=false：
- "你好"、"嗨"、"在吗"、"你是谁"、"测试" → 纯粹的打招呼，与家务无关
- "今天谁洗碗？"、"你吃饭了吗"、"现在几点了" → 疑问句，不是反馈已完成家务
- "帮我记一下"、"帮我记一笔" → 指令模糊，无法确认具体家务
- "该洗碗了"、"去扫地"、"你快去洗碗" → 命令，不是已完成
- "提醒我明天拖地"、"记得提醒我洗碗" → 提醒，不是已完成
- "我等会儿去洗碗"、"我准备拖地"、"我一会儿扫" → 计划/打算，未完成
- "洗碗了吗？"、"衣服洗了没"、"地拖了吗" → 疑问，不是已完成
- "厨房好乱"、"地好脏"、"我好累"、"今天真忙" → 抱怨/感慨，不是具体家务
- "好"、"知道了"、"收到"、"可以"、"不行" → 简短回复，无家务信息

## 严格禁止映射的任务（放入 ignored）
以下任务当前阶段不支持，不要映射到支持任务：
- 擦桌子、擦台面、整理被子、铺床、换床单
- 买菜、清理卫生间、清理厨房、铲猫砂、喂猫、遛狗
- 按摩、游戏、记账、维修、收快递、任何与家务无关的事

正确示例：
- "我擦了桌子" → ignored=["擦桌子"]
- "我买了菜" → ignored=["买菜"]
- "我清理了卫生间" → ignored=["清理卫生间"]
- "我铲了猫砂" → ignored=["铲猫砂"]

## 模糊表达处理
以下表达不要强行归类，应设 need_confirm=true：
- "我收拾了一下"、"我打扫了一下"
- "我把家里弄了一下"、"厨房弄好了"、"家里清理了一下"
- "房间里整理好了"、"我大概弄了一下"
- 这些可能包含支持任务，但缺少明确行为边界

## 只计分规则
必须是说话人表达自己已经完成的家务：
- "我刚刚/已经/弄好了/处理完了/搞定了"可作为完成信号
- 但"弄好了/处理完了/搞定了"必须能明确对应支持任务
- 正例："我洗了碗"、"饭后碗筷我都处理了"、"衣服洗好了"
- 反例："你好"、"提醒我洗碗"、"我等会儿洗碗"、"厨房好乱"

## 输出格式
必须返回 JSON（不要 markdown，不要解释），严格遵循以下结构：
{{
  "tasks": [
    {{ "task_type": "洗碗", "confidence": 0.95, "evidence": "饭后碗筷我都处理了" }}
  ],
  "ignored": [],
  "need_confirm": false
}}

要求：
- task_type 必须属于给定任务类型列表
- 不允许输出给定列表以外的任务类型
- confidence 取值 0~1，反映判断的确定性
- evidence 引用用户原文中的依据
- ignored 记录不支持的任务或原因（字符串数组）
- need_confirm=true 表示语义模糊可能包含家务但无法稳定映射"""


def _extract_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        text = re.sub(r"^.*?```(?:json)?\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*```.*$", "", text, flags=re.DOTALL)
    return text.strip()


def _validate_tasks(
    tasks: list[dict], valid_types: list[str]
) -> tuple[list[ParsedChoreTask], list[str]]:
    valid: list[ParsedChoreTask] = []
    ignored: list[str] = []
    for t in tasks:
        task_type = str(t.get("task_type", "")).strip() if isinstance(t.get("task_type"), str) else ""
        if not task_type:
            continue
        if task_type not in valid_types:
            ignored.append(task_type)
            continue
        confidence = t.get("confidence", 1.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (ValueError, TypeError):
            confidence = 1.0
        evidence = str(t.get("evidence", "")).strip() if isinstance(t.get("evidence"), str) else ""
        valid.append(ParsedChoreTask(task_type=task_type, confidence=confidence, evidence=evidence))
    return valid, ignored


class LLMParser:
    def __init__(self) -> None:
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._client = httpx.AsyncClient(timeout=30.0)

    async def parse_chore_text(
        self, text: str, task_types: list[str] | None = None
    ) -> LLMParseResult:
        if not self._api_key:
            logger.error("LLM_API_KEY not configured")
            return LLMParseResult(need_confirm=True, raw_response="LLM_API_KEY not configured")

        valid_types = task_types or DEFAULT_TASK_TYPES
        system_prompt = SYSTEM_PROMPT.format(task_types="、".join(valid_types))
        user_prompt = f"请解析以下家务描述：{text}"

        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            return LLMParseResult(need_confirm=True, raw_response=str(e))

        return self._parse_response(content, valid_types)

    def _parse_response(
        self, content: str, valid_types: list[str]
    ) -> LLMParseResult:
        raw = content
        try:
            json_str = _extract_json(content)
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("LLM JSON parse failed: %s, raw=%s", e, content)
            return LLMParseResult(need_confirm=True, raw_response=raw)

        raw_tasks = data.get("tasks", []) if isinstance(data, dict) else []
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        tasks, ignored = _validate_tasks(raw_tasks, valid_types)

        extra_ignored = data.get("ignored", [])
        if isinstance(extra_ignored, list):
            ignored.extend(str(x) for x in extra_ignored if isinstance(x, str) and x)

        need_confirm = bool(data.get("need_confirm", False)) if isinstance(data, dict) else True

        return LLMParseResult(
            tasks=tasks,
            ignored=ignored,
            need_confirm=need_confirm,
            raw_response=raw,
        )


llm_parser = LLMParser()
