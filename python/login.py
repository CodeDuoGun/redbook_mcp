#!/usr/bin/env python3
"""登录入口：对应 Go 版本的 cmd/login/main.go

以有界面模式（非无头）打开浏览器，引导用户完成小红书扫码登录，
登录成功后自动保存 cookies。

用法:
    python login.py [--bin /path/to/chrome]
    uv run python login.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from loguru import logger

# 配置日志输出到 stderr
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)


async def main(bin_path: str | None = None) -> None:
    from playwright.async_api import async_playwright

    from cookies import get_cookies_file_path, new_cookie_manager
    from xiaohongshu.login import LoginAction

    # 覆盖环境变量：登录时必须有界面
    os.environ["HEADLESS"] = "false"
    if bin_path:
        os.environ["CHROME_BIN"] = bin_path

    # 复用 browser.py 的工厂，但强制非无头
    from browser import new_browser_session

    logger.info("正在启动浏览器（有界面模式）...")
    session = await new_browser_session()

    try:
        page = await session.new_page()

        action = LoginAction(page)

        # 检查当前登录状态
        logger.info("检查当前登录状态...")
        status = await action.check_login_status()
        logger.info(f"当前登录状态: {'已登录' if status else '未登录'}")

        if status:
            logger.info("已处于登录状态，无需重新登录。")
            return

        # 开始登录流程：跳转到登录页，等待用户扫码
        logger.info("开始登录流程，请在浏览器中用小红书 App 扫码...")
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="load")

        success = await action.wait_for_login(timeout=240.0)

        if not success:
            logger.error("登录超时（240秒），请重新运行并尽快扫码。")
            sys.exit(1)

        # 保存 cookies
        cookies = await session.get_cookies()
        cm = new_cookie_manager()
        cm.save_cookies(cookies)
        cookies_path = get_cookies_file_path()
        logger.info(f"登录成功！Cookies 已保存至: {cookies_path}")

        # 再次确认登录状态
        confirmed = await action.check_login_status()
        if confirmed:
            logger.info("登录状态确认：✅ 已登录")
        else:
            logger.warning("登录流程完成，但登录状态确认失败，请检查 cookies。")

    finally:
        await session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书扫码登录工具")
    parser.add_argument(
        "--bin",
        dest="bin_path",
        default="",
        help="Chrome/Chromium 可执行文件路径（不填则使用 Playwright 自带 Chromium）",
    )
    args = parser.parse_args()

    asyncio.run(main(bin_path=args.bin_path or None))

