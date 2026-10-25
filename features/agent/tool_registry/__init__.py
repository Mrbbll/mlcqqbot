"""追踪当前 Agent 请求中连续相同工具调用，并提供渐进提醒。"""

class RepeatedCalls:
    """按当前请求的真实调用顺序追踪连续重复，不跨请求继承计数。"""

    def __init__(self):
        """初始化上一条调用签名和连续次数。"""
        self.signature = None
        self.count = 0

    def observe(self, signature: str) -> str:
        """更新连续次数，并在第三、四、五次及以后给出不同强度的提醒。"""
        self.count = self.count + 1 if signature == self.signature else 1
        self.signature = signature
        if self.count >= 5:
            return f"\n[重复调用提醒：连续 {self.count} 次相同工具和参数。仅在确实获得新信息时继续，否则请更换策略或说明限制。]"
        if self.count >= 4:
            return "\n[重复调用提醒：连续 4 次相同工具和参数。除非重复查询确有必要，请停止重复，调整参数、换工具或总结缺失信息。]"
        if self.count >= 3:
            return "\n[重复调用提醒：连续 3 次相同工具和参数。请检查结果是否新增信息，考虑调整参数或更换方法。]"
        return ""
