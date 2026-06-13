# 修复 OPGG API 连接超时问题

## 功能概述

修复 OPGG 功能在访问 `lol-api-champion.op.gg` 时出现的连接超时错误（`[WinError 121] 信号灯超时时间已到`），通过添加超时配置和重试机制提高网络请求的健壮性。

## 实现步骤

1. 在 `app/lol/opgg.py` 文件顶部添加 `asyncio` 导入
2. 修改 `Opgg.start()` 方法，为 `aiohttp.ClientSession` 设置 15 秒超时
3. 修改 `Opgg.__get()` 方法，添加最多 3 次重试机制，每次重试间隔 1 秒

## 遇到的问题及解决方案

### 问题描述

日志 `log\Seraphine_2026-06-13_ERROR.log` 中记录了 4 次 OPGG API 连接超时错误：
```
aiohttp.client_exceptions.ClientConnectorError: Cannot connect to host lol-api-champion.op.gg:443 ssl:False [信号灯超时时间已到]
```

### 原因分析

- `aiohttp.ClientSession` 创建时未设置 `timeout` 参数，默认无超时限制
- `__get()` 方法没有重试机制，网络异常直接抛出
- 网络波动或服务器响应慢时会导致功能完全不可用

### 解决方案

```python
# 添加超时配置
async def start(self):
    timeout = aiohttp.ClientTimeout(total=15)
    self.session = aiohttp.ClientSession("https://lol-api-champion.op.gg", timeout=timeout)

# 添加重试机制
async def __get(self, url, params=None):
    for i in range(3):
        try:
            res = await self.session.get(url, params=params, ssl=False, proxy=None)
            return await res.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if i == 2:
                raise
            await asyncio.sleep(1)
```

## 经验总结

- 对于外部 API 调用，应始终设置合理的超时时间
- 网络请求建议添加重试机制以提高容错性
- 定期检查错误日志可以及时发现和修复问题

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/lol/opgg.py` | 修改 | 添加 asyncio 导入、超时配置、重试机制 |

## 后续优化建议

- 可考虑为 OPGG 功能添加代理配置支持，解决部分地区无法访问的问题
- 可添加缓存过期机制，避免长时间使用过期数据
