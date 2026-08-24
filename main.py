"""
QQ 官方机器人 — 主入口
Minecraft 服务器查询机器人，移植自 NoneBot 项目

使用 qq-botpy SDK 连接 QQ 开放平台
支持群聊 @消息 和私聊消息
"""
import re
import asyncio
import traceback
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import logging

import botpy
from botpy import Client, Intents
from botpy.message import GroupMessage, C2CMessage

from config import QQ_BOT_APPID, QQ_BOT_SECRET
from handlers.server_query import (
    handle_list, handle_shijian, handle_ip,
    handle_map, handle_help,
)
from handlers.host_status import handle_status
from handlers.mcsm_control import (
    handle_execute, handle_open, handle_stop, handle_kill,
)
from utils.markdown import markdown_payload
from utils.keyboard import command_from_interaction, help_keyboard_payload

# 日志
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_app_logger() -> logging.Logger:
    """为业务日志配置独立文件，避免与 botpy SDK 日志混淆。"""
    logger = logging.getLogger("mlcbot")
    logger.setLevel(logging.INFO)

    log_path = Path(__file__).with_name("mlcbot.log").resolve()
    has_file_handler = any(
        isinstance(handler, TimedRotatingFileHandler)
        and Path(handler.baseFilename).resolve() == log_path
        for handler in logger.handlers
    )
    if not has_file_handler:
        handler = TimedRotatingFileHandler(
            log_path,
            when="D",
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)

    return logger


_log = configure_app_logger()


# ==================== 命令解析 ====================

def clean_message(content: str) -> str:
    """清理消息内容：去除 @mention 标签和首尾空白"""
    # 去除 <@!bot_id> 或 <@bot_id> 格式的 mention
    content = re.sub(r'<@!?\w+>', '', content)
    # 去除 @机器人名称 格式（纯文本 @）
    content = re.sub(r'@\S+', '', content)
    return content.strip()


def should_reply(content: str) -> bool:
    """检查消息是否包含有效指令，决定是否回复"""
    content = clean_message(content)
    commands = [
        "list", "视奸", "ip", "status", "map", "help",
        "服务器地图", "指令帮助",
        "/执行", "/开启", "/停止", "/终止",
    ]
    for cmd in commands:
        if content.startswith(cmd):
            return True
    return False


# ==================== 命令路由 ====================

async def route_command(content: str, user_id: str) -> str | None:
    """
    根据消息内容路由到对应的处理器
    返回响应文本，如果没有匹配的命令返回 None
    """
    content = clean_message(content)
    if content and not content.startswith("/"):
        content = f"/{content}"

    # 帮助（兼容指令面板的 help）
    if content.startswith(("/指令帮助", "/help")):
        return await handle_help()

    # 服务器地图（兼容指令面板的 map）
    if content.startswith(("/服务器地图", "/map")):
        return await handle_map()

    # list - 全部服务器状态
    if content.startswith("/list"):
        return await handle_list()

    # 视奸 - 在线玩家
    if content.startswith("/视奸"):
        return await handle_shijian()

    # ip - 服务器延迟
    if content.startswith("/ip"):
        return await handle_ip()

    # status - 宿主机状态
    if content.startswith("/status"):
        return await handle_status()

    # MCSM 面板命令（需超级用户权限）
    if content.startswith("/执行"):
        args = content[len("/执行"):].strip()
        return await handle_execute(args, user_id)

    if content.startswith("/开启"):
        args = content[len("/开启"):].strip()
        return await handle_open(args, user_id)

    if content.startswith("/停止"):
        args = content[len("/停止"):].strip()
        return await handle_stop(args, user_id)

    if content.startswith("/终止"):
        args = content[len("/终止"):].strip()
        return await handle_kill(args, user_id)

    return None


def is_help_command(content: str) -> bool:
    """判断消息是否为帮助命令，用于给帮助回复附加内联键盘。"""
    content = clean_message(content)
    if content and not content.startswith("/"):
        content = f"/{content}"
    return content.startswith(("/指令帮助", "/help"))


def command_reply_payload(content: str, reply_text: str, user_id: str = "") -> dict:
    """构造命令回复；帮助命令额外附带公开查询按钮。"""
    payload = markdown_payload(reply_text)
    if is_help_command(content):
        payload["keyboard"] = help_keyboard_payload(user_id)
    return payload


# ==================== Bot 客户端 ====================

class MLCBot(Client):
    """MLC Minecraft 服务器查询机器人"""

    async def on_ready(self):
        _log.info(f"机器人已上线！AppID: {QQ_BOT_APPID}")

    async def on_group_add_robot(self, event):
        """记录机器人加入群聊时下发的群 OpenID。"""
        _log.info(
            f"[机器人入群] group={event.group_openid} operator={event.op_member_openid}"
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        """处理群聊 @机器人 消息"""
        content = message.content
        user_id = message.author.member_openid if message.author else ""
        group_id = message.group_openid

        _log.info(f"[群消息] group={group_id} user={user_id} content={content}")

        try:
            reply_text = await route_command(content, user_id)
            if reply_text:
                payload = command_reply_payload(content, reply_text, user_id)
                if "keyboard" in payload:
                    _log.info("[帮助键盘] group=%s user=%s buttons=5", group_id, user_id)
                await message.reply(**payload)
        except Exception:
            _log.error(f"处理群消息异常: {traceback.format_exc()}")
            await message.reply(**markdown_payload("⚠️ **处理请求时发生错误**\n\n请稍后再试"))

    async def on_c2c_message_create(self, message: C2CMessage):
        """处理私聊消息"""
        content = message.content
        user_id = message.author.user_openid if message.author else ""

        _log.info(f"[私聊] user={user_id} content={content}")

        try:
            reply_text = await route_command(content, user_id)
            if reply_text:
                payload = command_reply_payload(content, reply_text, user_id)
                if "keyboard" in payload:
                    _log.info("[帮助键盘] c2c user=%s buttons=5", user_id)
                await message.reply(**payload)
        except Exception:
            _log.error(f"处理私聊异常: {traceback.format_exc()}")
            await message.reply(**markdown_payload("⚠️ **处理请求时发生错误**\n\n请稍后再试"))

    async def _send_interaction_reply(self, interaction, payload: dict) -> None:
        """把按钮命令的结果发送回触发按钮的群聊或私聊。"""
        if interaction.group_openid:
            await self.api.post_group_message(
                group_openid=interaction.group_openid,
                **payload,
            )
        elif interaction.user_openid:
            await self.api.post_c2c_message(
                openid=interaction.user_openid,
                **payload,
            )
        else:
            _log.warning("按钮事件缺少群 OpenID 和用户 OpenID: %r", interaction)

    async def on_interaction_create(self, interaction):
        """处理帮助消息中的内联按钮点击。"""
        # 官方规定只有 type=11 消息按钮事件需要确认；其他互动事件不处理。
        if interaction.type != 11:
            return

        command = command_from_interaction(interaction)

        # 先确认按钮事件，再执行可能耗时的服务器查询，避免回调超时。
        try:
            await self.api.on_interaction_result(interaction.id, 0 if command else 1)
        except Exception:
            _log.error(f"确认按钮事件异常: {traceback.format_exc()}")

        if not command:
            _log.warning("收到未识别的按钮事件: %r", interaction)
            return

        user_id = interaction.group_member_openid or interaction.user_openid or ""
        try:
            reply_text = await route_command(command, user_id)
            if reply_text:
                await self._send_interaction_reply(
                    interaction,
                    command_reply_payload(command, reply_text),
                )
        except Exception:
            _log.error(f"处理按钮事件异常: {traceback.format_exc()}")
            await self._send_interaction_reply(
                interaction,
                markdown_payload("⚠️ **处理请求时发生错误**\n\n请稍后再试"),
            )


# ==================== 启动入口 ====================

def main():
    """启动机器人"""
    # Python 3.12+ 需手动创建事件循环（botpy 内部用 get_event_loop）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 设置 Intents — public_messages 涵盖群聊 @消息和私聊消息
    intents = Intents.none()
    intents.public_messages = True
    intents.interaction = True

    client = MLCBot(intents=intents)
    _log.info(f"正在启动机器人... AppID: {QQ_BOT_APPID}")
    client.run(appid=QQ_BOT_APPID, secret=QQ_BOT_SECRET)


if __name__ == "__main__":
    main()
