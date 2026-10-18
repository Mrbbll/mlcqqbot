"""为指定 QQ 群创建机器人指令面板（一次性执行）。"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from botpy.http import BotHttp, Route
from config import QQ_BOT_APPID, QQ_BOT_SECRET, QQ_GROUP_OPENIDS


COMMAND_PANEL_ITEMS = [
    {"type": "command", "name": "list", "desc": "查看各服域名、在线人数和玩家名称"},
    {"type": "command", "name": "视奸", "desc": "查看各服在线人数和玩家名称"},
    {"type": "command", "name": "ip", "desc": "查看各服连接域名"},
    {"type": "command", "name": "status", "desc": "查看宿主机运行状态"},
    {"type": "command", "name": "map", "desc": "查看地图和文档链接"},
    {"type": "command", "name": "help", "desc": "查看全部可用指令"},
    {"type": "command", "name": "agent", "desc": "云端 AI 助手（仅管理员）"},
    {"type": "command", "name": "执行", "desc":"执行命令到实例"},
    {"type": "command", "name": "投票", "desc": "管理员发起整合包投票"},
    {"type": "command", "name": "投票结果", "desc": "管理员查看当前投票结果"},
    {"type": "command", "name": "开始钓鱼", "desc": "开始钓鱼小游戏"},
]


def build_command_panel_payload(group_openids: list[str]) -> dict[str, Any]:
    """构造 QQ OpenAPI 的群聊指令面板请求体。"""
    group_openids = [group_openid.strip() for group_openid in group_openids if group_openid.strip()]
    if not group_openids:
        raise ValueError("未配置 QQ_GROUP_OPENIDS，请先在 .env 中填写群 OpenID。")

    return {
        "scope": "group",
        "target_type": "specific",
        "group_openids": group_openids,
        "panel": {"items": COMMAND_PANEL_ITEMS},
    }


async def create_command_panel(payload: dict[str, Any]) -> Any:
    """调用 QQ OpenAPI 创建群聊指令面板。"""
    if not QQ_BOT_APPID:
        raise ValueError("未配置 QQ_BOT_APPID。")
    if not QQ_BOT_SECRET:
        raise ValueError("未配置 QQ_BOT_SECRET。")

    http = BotHttp(timeout=10, app_id=QQ_BOT_APPID, secret=QQ_BOT_SECRET)
    try:
        route = Route("POST", "/v2/panels")
        return await http.request(route, json=payload)
    finally:
        await http.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建 QQ 群聊机器人指令面板")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出请求体，不调用 QQ OpenAPI",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        payload = build_command_panel_payload(QQ_GROUP_OPENIDS)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        asyncio.run(create_command_panel(payload))
    except ValueError as exc:
        print(f"❌ 创建指令面板失败：{exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"❌ 创建指令面板失败：{exc}")
        raise SystemExit(1) from exc

    print(f"✅ 已为 {len(payload['group_openids'])} 个群创建指令面板。")


if __name__ == "__main__":
    main()
