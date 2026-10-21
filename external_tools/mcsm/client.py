"""MCSM 面板 HTTP API 客户端。"""
import requests

from config import MCSM_API_SECRET, MCSM_PANEL_URL


def _request(
    operation: str,
    uuid: str,
    daemon_id: str,
    command: str | None = None,
):
    """请求指定 MCSM 实例操作接口。"""
    url = f"{MCSM_PANEL_URL}/api/protected_instance/{operation}"
    params = {
        "apikey": MCSM_API_SECRET,
        "uuid": uuid,
        "daemonId": daemon_id,
    }
    if command is not None:
        params["command"] = command
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    return requests.get(url=url, params=params, headers=headers)


def send_mcsm_command(uuid: str, daemon_id: str, command: str):
    """向 MCSM 实例发送控制台命令。"""
    return _request("command", uuid, daemon_id, command)


def send_mcsm_open(uuid: str, daemon_id: str):
    """开启 MCSM 实例。"""
    return _request("open", uuid, daemon_id)


def send_mcsm_stop(uuid: str, daemon_id: str):
    """停止 MCSM 实例。"""
    return _request("stop", uuid, daemon_id)


def send_mcsm_kill(uuid: str, daemon_id: str):
    """终止 MCSM 实例。"""
    return _request("kill", uuid, daemon_id)
