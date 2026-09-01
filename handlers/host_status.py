"""
宿主机状态处理器
处理 status 命令 — 查询机器人所在服务器 CPU/内存/磁盘/运行时长
移植自 NoneBot 项目 mybot/plugins/mlc/status.py
"""
import time
import psutil

from utils import messages


async def handle_status() -> str:
    """处理 status 命令 — 返回宿主机运行状态。"""
    logical_cores = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()
    cpu_frequency = (
        (cpu_freq.current, cpu_freq.min, cpu_freq.max)
        if cpu_freq is not None
        else None
    )
    cpu_percent = psutil.cpu_percent(interval=0.5)

    disk_usage = psutil.disk_usage('/')
    disk_used = round(disk_usage.used / (1024 ** 3), 2)
    disk_free = round(disk_usage.free / (1024 ** 3), 2)

    mem = psutil.virtual_memory()
    total_mem = round(mem.total / (1024 ** 3), 2)
    used_mem = round(mem.used / (1024 ** 3), 2)

    boot_ts = psutil.boot_time()
    current_ts = time.time()
    boot_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_ts))
    uptime = int(current_ts - boot_ts)

    return messages.host_status(
        logical_cores=logical_cores,
        cpu_frequency=cpu_frequency,
        cpu_percent=cpu_percent,
        disk_used_gb=disk_used,
        disk_free_gb=disk_free,
        disk_percent=disk_usage.percent,
        memory_used_gb=used_mem,
        memory_total_gb=total_mem,
        memory_percent=mem.percent,
        boot_time=boot_time,
        uptime_seconds=uptime,
    )
