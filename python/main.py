"""程序入口，对应 Go 版本的 main.go"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv
from loguru import logger

# 加载 .env 文件（如果存在）
load_dotenv()

# 配置日志：输出到 stderr，避免污染 MCP stdout
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)


def main() -> None:
    from mcp_server import run_mcp_server
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()

