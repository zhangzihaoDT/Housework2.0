"""一次性历史结算验证脚本。

两种模式：
  --preview  只查看结果，不推送飞书
  --send     推送到配置的飞书群（卡片标记为"历史验证"）

用法：
  uv run python scripts/run_settlement_once.py --days 14 --preview
  uv run python scripts/run_settlement_once.py --days 14 --send
"""

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="历史结算验证")
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="统计最近 N 个完整自然日（默认 14）",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true", help="仅预览，不推送")
    group.add_argument("--send", action="store_true", help="推送飞书消息卡片")
    return parser.parse_args()


def compute_time_range(days: int) -> tuple[int, int, str, str]:
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = today_start - timedelta(days=days)
    start_ms = int(period_start.timestamp() * 1000)
    end_ms = int(today_start.timestamp() * 1000)
    start_str = period_start.strftime("%Y-%m-%d")
    end_str = today_start.strftime("%Y-%m-%d")
    return start_ms, end_ms, start_str, end_str


def build_verification_card(
    period_label: str,
    summary: list[dict],
    total_points: int,
    record_count: int,
    type_breakdown: list[tuple[str, int]],
) -> dict:
    member_lines = []
    for rank, item in enumerate(summary):
        emoji = "🥇" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else "  "
        prefix = f"{emoji} " if emoji.strip() else "  "
        member_lines.append(f"{prefix}**{item['member_name']}**　{item['points']} 分　{item['count']} 次")

    member_section = "\n\n".join(member_lines) if member_lines else "暂无记录"

    type_lines = [f"{t}　{c} 项" for t, c in type_breakdown[:8]]
    type_section = "\n".join(type_lines)

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": "🧪 小哈皮历史积分验证",
            },
        },
        "elements": [
            {"tag": "markdown", "content": f"**统计周期**\n{period_label}"},
            {"tag": "hr"},
            {"tag": "markdown", "content": member_section},
            {"tag": "hr"},
            {"tag": "markdown", "content": f"**任务类型分布**\n{type_section}"},
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": (
                    f"本期共记录 **{record_count} 项家务**，累计 **{total_points} 分**\n\n"
                    f"_本消息为历史数据验证，不触发正式清零。_"
                ),
            },
        ],
    }


async def main():
    args = parse_args()

    from app.config import settings
    from app.chore_service import get_member_map
    from app.bitable_client import bitable_client
    from app.feishu_client import feishu_client

    start_ms, end_ms, start_str, end_str = compute_time_range(args.days)

    last_date = (datetime.strptime(end_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    period_label = f"{start_str} ～ {last_date}"

    print("\n历史结算验证")
    print(f"统计周期：{start_str} 00:00 ～ {end_str} 00:00（不含结束）")
    print(f"显示范围：{start_str} ～ {last_date}")
    print()

    if not bitable_client.is_configured:
        print("错误：多维表格未配置")
        sys.exit(1)

    print(f"app_token（前缀）: {settings.feishu_bitable_app_token[:12]}...")
    print(f"chore_records table_id: {settings.feishu_table_chore_records}")
    print("查询字段: created_at")
    print(f"查询区间: [{start_ms}, {end_ms}) 毫秒时间戳")
    print(f"对应 UTC+8 时间: {start_str} 00:00:00 ～ {end_str} 00:00:00")
    print()

    records = await bitable_client.find_chore_records_by_time_range(start_ms, end_ms)
    print(f"查询到 {len(records)} 条家务记录\n")

    member_map = get_member_map()
    member_names = list(member_map.values()) if member_map else []


    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    task_types: list[str] = []
    record_count = 0

    for m in member_names:
        totals[m] = 0
        counts[m] = 0

    for r in records:
        fields = r.get("fields", {})
        raw_member = fields.get("member_name", "")
        task_type = fields.get("task_type", "")
        points = fields.get("points", 0)

        if member_map and raw_member in member_map:
            member_name = member_map[raw_member]
        elif member_map and len(raw_member) == 11 and "..." in raw_member:
            prefix, suffix = raw_member[:4], raw_member[-4:]
            matched = next((k for k in member_map if k.startswith(prefix) and k.endswith(suffix)), None)
            member_name = member_map[matched] if matched else raw_member
        else:
            member_name = raw_member

        if not member_name:
            continue

        pts = 0
        if isinstance(points, (int, float)):
            pts = int(points)
        elif isinstance(points, str):
            pts = int(float(points)) if points.replace(".", "", 1).isdigit() else 0
        totals[member_name] = totals.get(member_name, 0) + pts
        counts[member_name] = counts.get(member_name, 0) + 1
        record_count += 1
        if task_type:
            task_types.append(task_type)

    total_points = sum(totals.values())

    sorted_members = sorted(
        totals.items(), key=lambda x: (-x[1], x[0])
    )
    summary_data = [
        {"member_name": m, "points": p, "count": counts.get(m, 0)}
        for m, p in sorted_members
    ]

    type_counter = Counter(task_types)
    type_breakdown = type_counter.most_common()

    print(f"{'排名':<6} {'成员':<12} {'积分':<8} {'家务次数':<8}")
    print("-" * 34)
    for rank, item in enumerate(summary_data, 1):
        print(f"{rank:<6} {item['member_name']:<12} {item['points']:<8} {item['count']:<8}")
    print()
    print(f"总积分：{total_points}")
    print(f"总记录数：{record_count}\n")

    print("任务类型分布：")
    print("-" * 20)
    for task_type, count in type_breakdown:
        print(f"  {task_type:<8} {count}")
    print()

    if args.preview:
        print("预览模式，未推送飞书。")
        print(f"如需推送：uv run python scripts/run_settlement_once.py --days {args.days} --send")
        return

    if args.send:
        if not settings.settlement_chat_id:
            print("错误：SETTLEMENT_CHAT_ID 未配置")
            sys.exit(1)

        card = build_verification_card(
            period_label=period_label,
            summary=summary_data,
            total_points=total_points,
            record_count=record_count,
            type_breakdown=type_breakdown,
        )

        result = await feishu_client.send_interactive_card(
            receive_id=settings.settlement_chat_id,
            card=card,
        )

        if result.get("code") == 0:
            msg_id = result.get("data", {}).get("message_id", "")
            logger.info("verification card sent: message_id=%s", msg_id)
            print(f"\n✅ 验证卡片已推送。飞书 message_id: {msg_id}")
        else:
            logger.error("send failed: %s", result)
            print(f"\n❌ 推送失败：{result.get('msg', '')}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
