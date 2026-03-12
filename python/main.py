import argparse
import os
import logging

from configs import init_headless, set_bin_path
from service import XiaohongshuService
from app_server import AppServer


def main():
    parser = argparse.ArgumentParser(description="Xiaohongshu MCP Server")

    parser.add_argument(
        "--headless",
        default=True,
        action="store_true",
        help="是否无头模式"
    )

    parser.add_argument(
        "--bin",
        default="",
        help="浏览器二进制路径"
    )

    parser.add_argument(
        "--port",
        default="18060",
        help="服务端口"
    )

    args = parser.parse_args()

    headless = args.headless
    bin_path = args.bin
    port = args.port

    # 如果没指定 bin，从环境变量读取
    if not bin_path:
        bin_path = os.getenv("ROD_BROWSER_BIN")

    # 初始化配置
    init_headless(headless)
    set_bin_path(bin_path)

    # 初始化服务
    xiaohongshu_service = XiaohongshuService()

    # 创建服务器
    app_server = AppServer(xiaohongshu_service)

    try:
        app_server.start(port)
    except Exception as e:
        logging.fatal(f"failed to run server: {e}")


if __name__ == "__main__":
    main()