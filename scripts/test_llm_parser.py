"""本地测试 LLM 解析 + 积分计算"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.chore_service import (
    calculate_total_points,
    format_chore_reply,
    get_default_task_types,
)
from app.llm_parser import llm_parser


async def test_one(label: str, text: str, expect_tasks: int = -1, expect_points: int = -1):
    print(f"\n{'='*60}")
    print(f"[{label}] 原始: {text}")
    print(f"{'='*60}")

    result = await llm_parser.parse_chore_text(text, get_default_task_types())

    print(f"  LLM 原始响应: {result.raw_response[:200]}")
    print(f"  任务数: {len(result.tasks)}")
    print(f"  忽略: {result.ignored}")
    print(f"  需确认: {result.need_confirm}")

    if result.tasks:
        for t in result.tasks:
            print(f"    - {t.task_type} (conf={t.confidence}, evi={t.evidence})")
        total = calculate_total_points(result.tasks)
        print(f"  积分: {total}")
        print(f"  回复:\n{format_chore_reply(result.tasks, total)}")
    else:
        print("  无任务")

    if expect_tasks >= 0:
        assert len(result.tasks) == expect_tasks, (
            f"expected {expect_tasks} tasks, got {len(result.tasks)}"
        )
    if expect_points >= 0:
        total = calculate_total_points(result.tasks)
        assert total == expect_points, (
            f"expected {expect_points} points, got {total}"
        )


async def main():
    print("=" * 60)
    print("LLM 解析器测试 — 13 类任务（清洁打扫合并）")
    print("=" * 60)

    if not os.environ.get("LLM_API_KEY") and not os.path.exists(".env"):
        print("\n⚠️  未检测到 .env 文件或 LLM_API_KEY，请先配置环境变量")
        return

    # A. 明确关键词，应计分
    print("\n\n>>> A. 明确关键词，应计分")
    await test_one("A1-洗碗+拖地", "我刚刚洗了碗，还拖了地", expect_tasks=2, expect_points=2)
    await test_one("A2-倒垃圾+收衣服", "倒垃圾、收衣服", expect_tasks=2, expect_points=2)
    await test_one("A3-做饭", "今天做了晚饭", expect_tasks=1, expect_points=1)
    await test_one("A4-扫地", "我扫了地", expect_tasks=1, expect_points=1)
    await test_one("A5-洗衣服+晾衣服", "我洗了衣服并晾了衣服", expect_tasks=2, expect_points=2)

    # B. 非关键词但语义明确，应计分
    print("\n\n>>> B. 非关键词但语义明确，应计分")
    await test_one("B1-语义洗碗", "饭后碗筷我都处理了", expect_tasks=1, expect_points=1)
    await test_one("B2-语义洗碗2", "餐具已经收拾干净了", expect_tasks=1, expect_points=1)
    await test_one("B3-语义做饭", "今天晚饭我弄的", expect_tasks=1, expect_points=1)
    await test_one("B4-语义洗衣服", "衣服我放洗衣机洗了", expect_tasks=1, expect_points=1)
    await test_one("B5-语义晾衣服", "洗好的衣服我挂起来了", expect_tasks=1, expect_points=1)
    await test_one("B6-语义倒垃圾", "垃圾我拿下去了", expect_tasks=1, expect_points=1)
    await test_one("B7-语义扫地", "客厅地面我用扫把清了一下", expect_tasks=1, expect_points=1)
    await test_one("B8-语义拖地", "地板我用拖把过了一遍", expect_tasks=1, expect_points=1)

    # C. 组合语义，应拆分计分
    print("\n\n>>> C. 组合语义，应拆分计分")
    await test_one("C1-做饭+洗碗", "晚饭我做的，饭后碗也洗了", expect_tasks=2, expect_points=2)
    await test_one("C2-洗衣服+晾衣服", "衣服洗好了，也晾上了", expect_tasks=2, expect_points=2)
    await test_one("C3-倒垃圾+扫地", "垃圾拿下去了，顺手扫了地", expect_tasks=2, expect_points=2)
    await test_one("C4-做饭+洗碗+拖地", "做了晚饭，洗了碗，拖了厨房地", expect_tasks=3, expect_points=3)

    # D. 明确不支持任务，不应计分
    print("\n\n>>> D. 明确不支持任务，不应计分")
    await test_one("D1-买菜", "我买了菜", expect_tasks=0)
    await test_one("D2-收快递", "我收了快递", expect_tasks=0)
    await test_one("D3-擦桌子", "我擦了桌子", expect_tasks=1, expect_points=1)
    await test_one("D4-清理卫生间", "我清理了卫生间", expect_tasks=1, expect_points=1)
    await test_one("D5-换床单", "我换了床单", expect_tasks=1, expect_points=1)

    # E. 非完成状态或模糊表达，不应计分/需确认
    print("\n\n>>> E. 非完成状态或模糊表达")
    await test_one("E1-计划", "我等会儿去洗碗", expect_tasks=0)
    await test_one("E2-提醒", "提醒我明天拖地", expect_tasks=0)
    await test_one("E3-疑问", "洗碗了吗？", expect_tasks=0)
    await test_one("E4-抱怨", "厨房好乱", expect_tasks=0)
    await test_one("E4b-抱怨-厨房该清了", "厨房该清理了", expect_tasks=0)
    await test_one("E4c-提醒-清理厨房", "提醒我清理厨房", expect_tasks=0)
    await test_one("E5-模糊-打扫", "我打扫了一下", expect_tasks=0)
    await test_one("E5b-模糊-打扫无对象", "打扫了一下", expect_tasks=0)
    await test_one("E6-模糊-收拾", "我把家里收拾了一下", expect_tasks=0)
    await test_one("E6b-模糊-收拾无对象", "收拾了一下", expect_tasks=0)
    await test_one("E7-模糊-厨房弄好", "厨房弄好了", expect_tasks=0)
    await test_one("E8-模糊-整理了一下", "我整理了一下", expect_tasks=0)
    await test_one("E9-状态-房间乱", "房间有点乱", expect_tasks=0)
    await test_one("E10-状态-柜子乱", "柜子好乱", expect_tasks=0)
    await test_one("E11-状态-还没叠", "衣服还没叠", expect_tasks=0)

    # F. 无家务：前缀，语义明确应计分
    print("\n\n>>> F. 无家务：前缀，语义明确应计分")
    await test_one("F1-无前缀洗碗", "我洗了碗", expect_tasks=1, expect_points=1)
    await test_one("F2-无前缀洗碗+拖地", "我刚刚洗了碗，还拖了地", expect_tasks=2, expect_points=2)
    await test_one("F3-无前缀做饭+洗碗", "晚饭我做的，饭后碗也洗了", expect_tasks=2, expect_points=2)
    await test_one("F4-无前缀洗衣服+晾衣服", "衣服洗好了，也晾上了", expect_tasks=2, expect_points=2)
    await test_one("F5-无前缀倒垃圾", "垃圾拿下去了", expect_tasks=1, expect_points=1)

    # G. 闲聊/非家务，不应计分
    print("\n\n>>> G. 闲聊/非家务，不应计分")
    await test_one("G1-打招呼-你好", "你好", expect_tasks=0)
    await test_one("G2-打招呼-你是谁", "你是谁", expect_tasks=0)
    await test_one("G3-疑问-今天谁洗碗", "今天谁洗碗？", expect_tasks=0)
    await test_one("G4-模糊指令-帮我记一下", "帮我记一下", expect_tasks=0)
    await test_one("G5-计划-我等会儿洗碗", "我等会儿去洗碗", expect_tasks=0)
    await test_one("G6-抱怨-厨房好乱", "厨房好乱", expect_tasks=0)
    await test_one("G7-简短回复-好", "好", expect_tasks=0)
    await test_one("G8-简短回复-知道了", "知道了", expect_tasks=0)

    # H. 整理收纳
    print("\n\n>>> H. 整理收纳")
    await test_one("H1-整理房间", "整理房间了", expect_tasks=1, expect_points=1)
    await test_one("H2-整理柜子", "柜子重新整理了", expect_tasks=1, expect_points=1)
    await test_one("H3-东西归位", "东西都归位了", expect_tasks=1, expect_points=1)
    await test_one("H4-杂物收好", "房间里的杂物收好了", expect_tasks=1, expect_points=1)
    await test_one("H5-收拾房间", "收拾房间了", expect_tasks=1, expect_points=1)

    # I. 叠衣铺床
    print("\n\n>>> I. 叠衣铺床")
    await test_one("I1-叠衣服", "衣服叠好了", expect_tasks=1, expect_points=1)
    await test_one("I2-铺床", "铺床了", expect_tasks=1, expect_points=1)
    await test_one("I3-叠被子", "被子叠好了", expect_tasks=1, expect_points=1)
    await test_one("I4-整理床铺", "整理床铺了", expect_tasks=1, expect_points=1)

    # J. 换洗床品
    print("\n\n>>> J. 换洗床品")
    await test_one("J1-换床单", "换床单了", expect_tasks=1, expect_points=1)
    await test_one("J2-换被套", "被套换了", expect_tasks=1, expect_points=1)
    await test_one("J3-换枕套", "枕套换了", expect_tasks=1, expect_points=1)
    await test_one("J4-换四件套", "换了四件套", expect_tasks=1, expect_points=1)

    # K. 清洁打扫
    print("\n\n>>> K. 清洁打扫")
    await test_one("K1-擦桌子", "擦桌子了", expect_tasks=1, expect_points=1)
    await test_one("K2-擦台面", "台面擦了", expect_tasks=1, expect_points=1)
    await test_one("K3-擦灶台", "擦了灶台", expect_tasks=1, expect_points=1)
    await test_one("K4-擦茶几", "茶几擦干净了", expect_tasks=1, expect_points=1)
    await test_one("K5-清理厨房", "清理厨房了", expect_tasks=1, expect_points=1)
    await test_one("K6-厨房清理", "厨房清理了", expect_tasks=1, expect_points=1)
    await test_one("K7-清理卫生间", "清理卫生间了", expect_tasks=1, expect_points=1)
    await test_one("K8-刷马桶", "刷马桶了", expect_tasks=1, expect_points=1)
    await test_one("K9-洗手台清理", "洗手台清理了", expect_tasks=1, expect_points=1)
    await test_one("K10-清理地漏", "地漏清理了", expect_tasks=1, expect_points=1)

    # M. 虎妞照护
    print("\n\n>>> M. 虎妞照护")
    await test_one("M1-铲屎", "铲屎了", expect_tasks=1, expect_points=1)
    await test_one("M2-铲猫砂", "铲猫砂了", expect_tasks=1, expect_points=1)
    await test_one("M3-虎妞换水", "虎妞饮水机换水了", expect_tasks=1, expect_points=1)
    await test_one("M4-给虎妞换水", "给虎妞换水了", expect_tasks=1, expect_points=1)
    await test_one("M5-给猫添粮", "给猫添粮了", expect_tasks=1, expect_points=1)
    await test_one("M6-喂猫", "喂猫了", expect_tasks=1, expect_points=1)

    # N. 虎妞照护不计分
    print("\n\n>>> N. 虎妞照护不计分")
    await test_one("N1-该铲猫砂了", "该铲猫砂了", expect_tasks=0)
    await test_one("N2-提醒换水", "提醒我给虎妞换水", expect_tasks=0)
    await test_one("N3-没水了", "虎妞饮水机没水了", expect_tasks=0)
    await test_one("N4-虎妞可爱", "虎妞好可爱", expect_tasks=0)

    # O. 组合任务新场景
    print("\n\n>>> O. 组合任务新场景")
    await test_one("O1-做饭+洗碗+虎妞", "晚饭做好了，碗也洗了，猫砂也铲了", expect_tasks=3, expect_points=3)
    await test_one("O2-收衣服+叠衣", "衣服收了，也叠好了", expect_tasks=2, expect_points=2)
    await test_one("O3-整理收纳+叠衣", "整理了柜子，顺手把衣服叠了", expect_tasks=2, expect_points=2)
    await test_one("O4-换洗床品+叠衣", "换了床单，又把被子叠好了", expect_tasks=2, expect_points=2)
    await test_one("O5-清洁打扫+扫地", "擦了桌子，也扫了地", expect_tasks=2, expect_points=2)
    await test_one("O6-清洁打扫+洗碗", "擦了灶台，又洗了碗", expect_tasks=2, expect_points=2)
    await test_one("O7-清洁打扫+拖地", "清理了厨房，又拖了地", expect_tasks=2, expect_points=2)
    await test_one("O8-清洁打扫+倒垃圾", "刷了马桶，也倒了垃圾", expect_tasks=2, expect_points=2)

    # P. 同类去重
    print("\n\n>>> P. 同类子动作去重")
    await test_one("P1-去重-虎妞照护", "铲了猫砂，又换了水，还添了粮", expect_tasks=1, expect_points=1)
    await test_one("P2-去重-清洁打扫-台面", "擦了桌子，擦了灶台，台面也擦了", expect_tasks=1, expect_points=1)
    await test_one("P3-去重-清洁打扫-卫生间", "刷了马桶，顺手把洗手台也擦了", expect_tasks=1, expect_points=1)
    await test_one("P4-去重-清洁打扫-混合", "擦了桌子，也擦了台面，还刷了马桶", expect_tasks=1, expect_points=1)

    print("\n\n" + "=" * 60)
    print("LLM 解析测试完成 ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
