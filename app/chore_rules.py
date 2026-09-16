"""本地规则家务解析器。

LLM 不可用（欠费/超时/异常）时的兜底解析，也用于快速识别裸任务名。
纯逻辑实现，便于单测，不产生任何网络调用。

设计要点：
- 别名表覆盖 13 类任务的常见说法（含备菜→做饭、擦地→拖地、刷马桶→清洁打扫等）。
- 按标点/连接词分句；同句内不同任务正常拆分。
- 显式重复（"拖了两次地"、"又扫了一遍"）按次数计分。
- 同类子动作去重：清洁打扫/虎妞照护等不同子动作默认只计 1 项。
- 排除提醒/计划/疑问/状态描述，避免误计分。
"""

import re

from app.chore_service import normalize_chore_input_text
from app.schemas import ParsedChoreTask

_MAX_REPEAT = 3

TASK_ALIASES: dict[str, list[str]] = {
    "做饭": [
        "做饭", "做了饭", "煮饭", "烧饭", "做菜", "炒菜", "煮菜", "下厨",
        "备菜", "备料", "切菜", "配菜", "弄饭", "做了晚饭", "做了午饭",
        "做了早饭", "准备晚饭", "准备午饭", "准备早饭",
    ],
    "洗碗": [
        "洗碗", "刷碗", "洗了碗", "刷了碗", "洗碗筷", "洗餐具", "洗盘子",
        "刷锅", "洗碗盘",
    ],
    "扫地": ["扫地", "扫了地", "扫一遍地", "扫扫地", "清扫地面", "扫地了"],
    "拖地": ["拖地", "拖了地", "拖地板", "擦地", "拖一遍地", "拖地了"],
    "倒垃圾": [
        "倒垃圾", "扔垃圾", "丢垃圾", "垃圾倒了", "垃圾扔了", "垃圾拿下去",
        "下楼丢垃圾", "垃圾丢了",
    ],
    "洗衣服": ["洗衣服", "洗衣", "洗了衣服", "开洗衣机", "衣服洗了", "洗脏衣服"],
    "晾衣服": [
        "晾衣服", "晾了衣服", "晒衣服", "晒了衣服", "挂衣服", "晾衣",
        "衣服晾上", "衣服晒了",
    ],
    "收衣服": ["收衣服", "收了衣服", "收衣", "衣服收了", "衣服拿回来", "衣服收回来"],
    "整理收纳": [
        "整理房间", "收拾房间", "整理卧室", "整理客厅", "整理柜子", "整理衣柜",
        "整理抽屉", "整理桌面", "整理杂物", "收纳", "归位", "收拾屋子",
        "房间收拾",
    ],
    "叠衣铺床": [
        "叠衣服", "叠了衣服", "叠衣", "叠被子", "叠了被子", "铺床", "铺了床",
        "整理床铺", "整理被子", "叠",
    ],
    "换洗床品": [
        "换床单", "换被套", "换枕套", "换四件套", "换床品", "洗床单",
        "换洗床品", "床单换了", "被套换了",
    ],
    "清洁打扫": [
        "清洁", "打扫", "擦桌子", "擦台面", "擦灶台", "擦茶几", "擦洗手台",
        "擦玻璃", "刷马桶", "刷厕所", "洗马桶", "清理厨房", "清理卫生间",
        "打扫卫生间", "打扫厨房", "清理地漏", "擦地漏", "清洁台面", "清理灶台",
        "打扫卫生",
    ],
    "虎妞照护": [
        "铲屎", "铲猫砂", "猫砂", "换水", "添粮", "喂猫", "虎妞照护",
        "清理猫砂", "猫砂盆", "给猫", "给虎妞",
    ],
}

_SPLIT_RE = re.compile(r"[，,。；;！!、\s]+|还有|然后|接着|顺便|顺手|并且|而且|以及|和|也")

# 两个及以上：数字 + 次/遍
_REPEAT_NUM_RE = re.compile(r"(两|二|三|四|五|[2-5])\s*(次|遍)")
_CN_NUM = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5}

# 又/再 ... 一遍/一次（同一动作再次发生）
_REPEAT_AGAIN_RE = re.compile(r"(又|再)[^，,。；;！!、]*?(一遍|一次)")

# 提醒/计划/疑问/状态描述等，命中则整句不计分
_NEGATIVE_MARKERS = (
    "该", "需要", "提醒", "记得", "别忘", "别", "不要", "等会", "等下",
    "待会", "一会", "马上", "稍后", "打算", "计划", "准备去", "想去", "想要",
    "想", "明天", "下次", "以后", "了吗", "了没", "没有", "还没", "没", "不用",
    "好乱", "好脏", "没做", "没弄", "吗", "？", "?",
)

# 匹配前去掉体貌助词与重复标记，容忍"擦了桌子"、"拖了两次地"、"又扫了一遍"
_PARTICLE_RE = re.compile(r"[了过着完]")
_REPEAT_TOKEN_RE = re.compile(r"(两|二|三|四|五|[2-5])\s*(次|遍)|一遍|一次|又|再")


def _normalize_for_match(text: str) -> str:
    text = _PARTICLE_RE.sub("", text)
    text = _REPEAT_TOKEN_RE.sub("", text)
    return text


# 别名展开为 (normalized_alias, task_type)，按长度降序，优先匹配更具体的说法
_ALIAS_INDEX: list[tuple[str, str]] = sorted(
    (
        (_normalize_for_match(alias), task)
        for task, aliases in TASK_ALIASES.items()
        for alias in aliases
    ),
    key=lambda x: len(x[0]),
    reverse=True,
)


def _match_task_types(clause: str) -> list[str]:
    normalized = _normalize_for_match(clause)
    matched: list[str] = []
    for alias, task in _ALIAS_INDEX:
        if alias and alias in normalized and task not in matched:
            matched.append(task)
    return matched


def _repeat_count(clause: str) -> int:
    """返回该句的额外重复标记产生的总次数（>=1）。"""
    m = _REPEAT_NUM_RE.search(clause)
    if m:
        raw = m.group(1)
        return _CN_NUM.get(raw, int(raw) if raw.isdigit() else 1)
    if _REPEAT_AGAIN_RE.search(clause):
        return 2
    return 1


def match_chores(text: str) -> list[ParsedChoreTask]:
    """将一段文本解析为家务任务列表；无法确定时返回空列表。"""
    normalized = normalize_chore_input_text(text)
    if not normalized:
        return []

    clauses = [c.strip() for c in _SPLIT_RE.split(normalized) if c.strip()]

    base: dict[str, int] = {}
    last_task: str | None = None
    for clause in clauses:
        if any(marker in clause for marker in _NEGATIVE_MARKERS):
            continue
        tasks = _match_task_types(clause)
        repeat = _repeat_count(clause)
        if not tasks:
            # 省略宾语的续说，如"扫了地，又扫了一遍" → 把重复归到上一项
            if repeat > 1 and last_task:
                base[last_task] = max(base.get(last_task, 1), repeat)
            continue
        for task in tasks:
            # 同类子动作默认去重为 1；只有显式重复才累计
            base[task] = max(base.get(task, 1), repeat)
        last_task = tasks[-1]

    results: list[ParsedChoreTask] = []
    for task, count in base.items():
        capped = max(1, min(_MAX_REPEAT, count))
        for _ in range(capped):
            results.append(ParsedChoreTask(task_type=task, confidence=1.0, evidence=normalized))
    return results
