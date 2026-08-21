"""
宿主机状态处理器
处理 status 命令 — 查询机器人所在服务器 CPU/内存/磁盘/运行时长
移植自 NoneBot 项目 mybot/plugins/mlc/status.py
"""
import time
import psutil

from utils.markdown import inline_code


async def handle_status() -> str:
    """处理 status 命令 — 返回宿主机运行状态。"""
    lines = ["# 宿主机运行状态", ""]

    # CPU 核心数
    logical_cores = psutil.cpu_count()
    lines.append(f"- **CPU 核心**：逻辑 {logical_cores} 核")

    # CPU 频率
    cpu_freq = psutil.cpu_freq()
    lines.append(
        f"- **CPU 频率**：当前 {cpu_freq.current} MHz，"
        f"最小 {cpu_freq.min} MHz，最大 {cpu_freq.max} MHz"
    )

    # CPU 占用率
    cpu_percent = psutil.cpu_percent(interval=0.5)
    lines.append(f"- **CPU 占用**：{cpu_percent}%")

    # 磁盘占用
    disk_usage = psutil.disk_usage('/')
    disk_used = round(disk_usage.used / (1024 ** 3), 2)
    disk_free = round(disk_usage.free / (1024 ** 3), 2)
    lines.append(
        f"- **磁盘**：已用 {disk_used}GB（{disk_usage.percent}%），"
        f"可用 {disk_free}GB"
    )

    # 内存占用
    mem = psutil.virtual_memory()
    total_mem = round(mem.total / (1024 ** 3), 2)
    used_mem = round(mem.used / (1024 ** 3), 2)
    lines.append(
        f"- **内存**：{used_mem}GB / {total_mem}GB（{mem.percent}%）"
    )

    # 运行时长
    boot_ts = psutil.boot_time()
    current_ts = time.time()
    boot_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_ts))
    uptime = int(current_ts - boot_ts)
    uptime_str = f"{uptime // 3600}小时{(uptime % 3600) // 60}分钟"
    lines.append(f"- **启动于**：{inline_code(boot_time)}")
    lines.append(f"- **运行时长**：{inline_code(uptime_str)}")

    return "\n".join(lines)
