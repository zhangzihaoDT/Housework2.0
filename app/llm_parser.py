"""调用 LLM 将自然语言解析为结构化家务任务或家庭提醒"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta

import httpx

from app.config import settings
from app.schemas import LLMParseResult, ParsedChoreTask, ReminderParsedResult

logger = logging.getLogger(__name__)

DEFAULT_TASK_TYPES = [
    "做饭", "洗碗", "扫地", "拖地", "倒垃圾",
    "洗衣服", "晾衣服", "收衣服", "整理收纳",
    "叠衣铺床", "换洗床品", "清洁打扫",
    "虎妞照护",
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

### 做饭（语义范围）
用户说以下内容都应理解为「做饭」：
- 做了饭、煮了饭、做了晚饭/午饭/早餐
- 今天晚饭我弄的、我做了两个菜
- 饭菜我准备的、我负责做菜

### 洗碗（语义范围）
用户说以下内容都应理解为「洗碗」：
- 洗碗、洗了碗、刷了碗、处理了碗筷、餐具收拾干净了
- 饭后碗筷都处理了、厨房的碗盘洗好了
- 把碗刷了、碗筷我搞定了

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

### 整理收纳（语义范围）
表示空间、柜子、桌面杂物、物品归位、收纳相关行为。可映射为「整理收纳」：
- 整理房间、收拾房间、整理卧室/客厅
- 整理柜子、整理衣柜、整理抽屉
- 整理桌面上的杂物、收纳、东西归位
- 把东西归位了、把杂物收好了
- 房间里的东西收拾好了、柜子重新整理了

注意：
- 「擦桌子」「擦台面」「清理厨房」不属于整理收纳，应归为清洁打扫
- 「换床单」不属于整理收纳，应归为换洗床品
- 如果只是说「整理了一下」「收拾了一下」，没有明确对象，need_confirm

### 叠衣铺床（语义范围）
表示衣物折叠、日常床铺整理、被子整理。可映射为「叠衣铺床」：
- 叠衣服、把衣服叠了、叠了衣服
- 整理床铺、铺床、把床铺好了
- 叠被子、被子叠好了、把被子整理了、整理被子

注意：
- 「换床单/换被套/换枕套」不属于叠衣铺床，应归为换洗床品
- 「收衣服」仍然归为收衣服
- 「洗衣服」仍然归为洗衣服
- 「晾衣服」仍然归为晾衣服

### 换洗床品（语义范围）
表示更换床单、被套、枕套、床品相关行为。可映射为「换洗床品」：
- 换床单、床单换了
- 换被套、被套换了
- 换枕套、枕套换了
- 换床品、床品换了
- 把床单被套换了、换了四件套

注意：
- 只是「铺床」「叠被子」「整理床铺」归为叠衣铺床
- 如果说「床单该换了」「提醒我换床单」，不计分

### 清洁打扫（语义范围）
表示厨房、卫生间、台面、桌面、灶台、马桶、洗手台、浴室等区域或表面的清洁行为。可映射为「清洁打扫」：

台面/桌面清洁：
- 擦桌子、桌子擦了、擦餐桌、擦茶几
- 擦台面、台面擦了、擦厨房台面、擦灶台、灶台擦了
- 把桌面擦干净了、把台面清理干净了

厨房清洁：
- 清理厨房、厨房清理了、打扫厨房、厨房打扫了、厨房收拾干净了
- 灶台清理了、油污擦了、厨房台面擦了

卫生间清洁：
- 清理卫生间、卫生间清理了、打扫卫生间
- 刷厕所、刷马桶、马桶刷了、洗马桶
- 清理洗手台、洗手台清理了
- 清理地漏、清理浴室、浴室清洁了

注意：
- 「扫地」仍然归为扫地
- 「拖地」仍然归为拖地
- 「洗碗」仍然归为洗碗
- 「整理桌面杂物」归为整理收纳
- 「清理厨房」如果语义明确是厨房清洁，可以归为清洁打扫
- 「厨房好乱」「厨房该清理了」「提醒我清理厨房」不计分
- 「打扫了一下」如果没有对象，仍然 need_confirm，不要强行归为清洁打扫
- 多个清洁打扫子动作（擦桌子+擦台面+刷马桶），只计 1 项清洁打扫

### 虎妞照护（语义范围）
虎妞是用户家的小猫。猫咪日常照护相关家务映射为「虎妞照护」：
- 铲屎、铲猫砂、清理猫砂、清理猫砂盆、猫砂盆清理了
- 给虎妞换水、给虎妞饮水机换水、饮水机换水
- 给猫换水、猫咪饮水机换水、虎妞的水换了
- 给虎妞添粮、给猫添粮、猫粮加了
- 喂猫（如果表达为已完成照护行为）

注意：
- 「虎妞好可爱」「虎妞在睡觉」不是家务
- 「虎妞吐了」「虎妞拉了」只是状态描述，不计分，除非明确说已经清理
- 「该铲猫砂了」「提醒我给虎妞换水」不计分
- 多个虎妞照护子动作（铲猫砂+换水+添粮），只计 1 项虎妞照护

## 组合任务拆分规则
一条描述可能包含多个已完成的家务，需要拆分成多个不同 task_type。

正确示例：
- "我刚刚洗了碗，还拖了地" → 洗碗 + 拖地
- "晚饭我做的，饭后碗也洗了" → 做饭 + 洗碗
- "衣服洗好了，也晾上了" → 洗衣服 + 晾衣服
- "垃圾拿下去了，顺手扫了地" → 倒垃圾 + 扫地
- "做了晚饭，洗了碗，拖了厨房地" → 做饭 + 洗碗 + 拖地
- "晚饭做好了，碗也洗了，猫砂也铲了" → 做饭 + 洗碗 + 虎妞照护
- "衣服收了，也叠好了" → 收衣服 + 叠衣铺床
- "整理了柜子，顺手把衣服叠了" → 整理收纳 + 叠衣铺床
- "换了床单，又把被子叠好了" → 换洗床品 + 叠衣铺床
- "擦了桌子，也扫了地" → 清洁打扫 + 扫地
- "擦了灶台，又洗了碗" → 清洁打扫 + 洗碗
- "清理了厨房，又拖了地" → 清洁打扫 + 拖地
- "刷了马桶，也倒了垃圾" → 清洁打扫 + 倒垃圾

## 同类子动作去重规则
同一句中的同类子动作只计 1 项：
- 多个虎妞照护子动作（铲猫砂+换水+添粮）→ 只记 1 项虎妞照护
- 多个清洁打扫子动作（擦桌子+擦台面+擦灶台）→ 只记 1 项清洁打扫
- 多个清洁打扫子动作（刷马桶+清理洗手台+清理地漏）→ 只记 1 项清洁打扫

但如果同一句包含不同 task_type，要正常拆分。

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
- "该铲猫砂了"、"提醒我给虎妞换水"、"虎妞饮水机没水了" → 提醒/状态，不是已完成
- "虎妞好可爱"、"虎妞在睡觉" → 非家务

## 严格禁止映射的任务（放入 ignored）
以下任务当前阶段不支持，不要映射到支持任务：
- 买菜、遛狗、收快递
- 维修、按摩、游戏、记账、任何与家务无关的事

正确示例：
- "我买了菜" → ignored=["买菜"]
- "厨房弄好了" → need_confirm=true（缺少明确行为边界）

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
- 反例："房间有点乱"、"柜子好乱"、"衣服还没叠" → 状态描述，不计分
- 反例："我整理了一下" → 语义模糊，need_confirm

## 裸任务名规则（重要）
如果用户只说了一个支持的任务类型名称本身（如「洗碗」「扫地」「拖地」「做饭」「倒垃圾」等），
没有其他内容，应视为该任务已完成，直接计分，confidence=1.0，need_confirm=false。
正例："洗碗" → 洗碗，已计分
正例："扫地" → 扫地，已计分
正例："拖地" → 拖地，已计分
正例："虎妞照护" → 虎妞照护，已计分
反例："洗" → 不能模糊映射，不计分
反例：空字符串或仅空格 → 不解析

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

    async def parse_reminder_text(
        self, text: str, today_date: str, weekday_cn: str
    ) -> ReminderParsedResult:
        if not self._api_key:
            logger.error("LLM_API_KEY not configured")
            return ReminderParsedResult(raw_response="LLM_API_KEY not configured")

        system_prompt = (
            REMINDER_SYSTEM_PROMPT.format(today_date=today_date, weekday_cn=weekday_cn)
        )
        user_prompt = f"请解析以下内容：{text}"

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
            logger.error("LLM reminder parse API call failed: %s", e)
            return ReminderParsedResult(raw_response=str(e))

        return self._parse_reminder_response(content)

    def _parse_reminder_response(self, content: str) -> ReminderParsedResult:
        raw = content
        try:
            json_str = _extract_json(content)
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("LLM reminder JSON parse failed: %s, raw=%s", e, content)
            return ReminderParsedResult(raw_response=raw)

        if not isinstance(data, dict):
            return ReminderParsedResult(raw_response=raw)

        is_reminder = bool(data.get("is_reminder", False))
        if not is_reminder:
            return ReminderParsedResult(is_reminder=False, raw_response=raw)

        return ReminderParsedResult(
            is_reminder=True,
            target_person=str(data.get("target_person", "")).strip(),
            event_text=str(data.get("event_text", "")).strip(),
            event_date=str(data.get("event_date", "")).strip(),
            remind_time=str(data.get("remind_time", "")).strip(),
            remind_text=str(data.get("remind_text", "")).strip(),
            raw_response=raw,
        )


REMINDER_SYSTEM_PROMPT = """你是一个家庭智能提醒解析引擎。

## 核心任务
判断用户输入是否在创建一条未来提醒（待办事项/行程），如果是，解析出结构化信息。

## 判断标准
是提醒的特征：
- 包含未来时间表达：明天、后天、下周三、下个月5号、7月12日等
- 描述一个未来要发生的事情、行程、安排
- 可能包含指定成员（如shuyao、zihao、妈妈、爸爸）或没有明确成员（即家庭全体）
- 包含"提醒我"字样的通常是提醒

不是提醒（is_reminder=false）的例子：
- 闲聊：你好、在吗、你是谁、测试
- 已完成事项：我洗了碗、我扫了地、衣服洗好了（这些是家务记录）
- 疑问句：今天谁洗碗？你吃饭了吗
- 抱怨/状态描述：厨房好乱、地好脏
- 简短回复：好、知道了、收到、可以

## 时间解析规则
今天的日期是 {today_date}，星期{weekday_cn}。计算相对日期时请基于此推导。

- 明天 → {today_date} + 1天
- 后天 → {today_date} + 2天
- 下周一~下周日 → 下一个对应的周几
- 下周 → 下周一的日期
- 下个月5号 → 下个月5号的日期
- 7月12日 → 今年7月12日（如果已过则明年）
- 2026年7月12日 → 直接使用

时间默认规则：
- 如果用户说"早上" → 08:00
- 如果用户说"上午" → 09:00
- 如果用户说"中午" → 12:00
- 如果用户说"下午" → 14:00
- 如果用户说"晚上" → 19:00
- 如果用户说X点 → X:00
- 如果用户说X点X分 → X:XX（保持原样）
- 如果用户没有指定时间 → 08:00（默认）

## 提醒对象解析规则
- 如果提到家庭成员名（如shuyao、zihao、妈妈、爸爸等），target_person设为该成员名
- 如果没有明确成员，target_person设为空字符串（表示家庭级提醒）
- "我"在提醒语境下不映射到具体成员，target_person设为""（家庭级）
- "全家"、"大家"、"我们" → target_person设为""（家庭级）

## 提醒文案生成规则
remind_text 是到点后群里显示的消息，要简洁自然：
- 成员级："今天 {{target_person}} {{event_text}}"，例如"今天 shuyao 去杭州"
- 家庭级："今天全家{{event_text}}"，例如"今天全家去迪士尼"
- 保持原文的自然表达风格

## 输出格式
{{
  "is_reminder": true 或 false,
  "target_person": "成员名（成员级）或空字符串（家庭级）",
  "event_text": "事项内容，简洁明了",
  "event_date": "YYYY-MM-DD格式",
  "remind_time": "HH:MM格式（24小时制）",
  "remind_text": "到点后发给群里的提醒消息正文"
}}

要求：
- 如果不确定是否提醒，is_reminder设为false
- event_date必须是有效的YYYY-MM-DD格式
- remind_time必须是有效的HH:MM格式
- remind_text不要超过100字
- 不是所有包含时间的句子都是提醒，注意区分"""


llm_parser = LLMParser()
