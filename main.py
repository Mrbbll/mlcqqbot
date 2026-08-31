"""QQ 官方机器人启动入口。"""
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from botpy import Intents

from bot_client import MLCBot
from config import QQ_BOT_APPID, QQ_BOT_SECRET

# 兼容已有调用方；具体实现已拆分到对应模块。
from handlers.command_router import route_command, should_reply
from utils.command_text import clean_message
from utils.reply_payload import (
    command_reply_payload,
    is_help_command,
    is_lottery_command,
)


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


def main():
    """创建 QQ 客户端并启动事件循环。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    intents = Intents.none()
    intents.public_messages = True
    intents.interaction = True

    client = MLCBot(intents=intents)
    _log.info("正在启动机器人... AppID: %s", QQ_BOT_APPID)
    client.run(appid=QQ_BOT_APPID, secret=QQ_BOT_SECRET)


if __name__ == "__main__":
    main()
