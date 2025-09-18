# -*- coding: UTF-8 -*-

from ping3 import ping, verbose_ping

# 简单用法
response_time = ping("www.baidu.com", timeout=2)  # 返回响应时间（毫秒）或 None
print(f"响应时间: {response_time}ms")

# 详细输出
verbose_ping("www.baidu.com")
