"""评论与回复功能，对应 Go 版本的 xiaohongshu/comment_feed.go"""

from __future__ import annotations

import asyncio

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.feed_detail import (
    _check_page_accessible,
    _check_end_container,
    _get_comment_count,
    _make_feed_detail_url,
    _scroll_to_comments_area,
)


class CommentFeedAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def post_comment(self, feed_id: str, xsec_token: str, content: str) -> None:
        """发表评论到 Feed"""
        url = _make_feed_detail_url(feed_id, xsec_token)
        logger.info(f"打开 feed 详情页: {url}")

        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
        await _check_page_accessible(self.page)

        # 点击评论输入框激活
        elem = await self.page.query_selector("div.input-box div.content-edit span")
        if elem is None:
            raise RuntimeError("未找到评论输入框，该帖子可能不支持评论或网页端不可访问")
        await elem.click()

        # 找到真正的输入区域
        inp = await self.page.query_selector("div.input-box div.content-edit p.content-input")
        if inp is None:
            raise RuntimeError("未找到评论输入区域")
        await inp.fill(content)
        await asyncio.sleep(1)

        submit = await self.page.query_selector("div.bottom button.submit")
        if submit is None:
            raise RuntimeError("未找到提交按钮")
        await submit.click()
        await asyncio.sleep(1)
        logger.info(f"评论发表成功 feed_id={feed_id}")

    async def reply_to_comment(
        self,
        feed_id: str,
        xsec_token: str,
        comment_id: str,
        user_id: str,
        content: str,
    ) -> None:
        """回复指定评论"""
        url = _make_feed_detail_url(feed_id, xsec_token)
        logger.info(f"打开 feed 详情页进行回复: {url}")

        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
        await _check_page_accessible(self.page)
        await asyncio.sleep(2)

        comment_el = await _find_comment_element(self.page, comment_id, user_id)
        if comment_el is None:
            raise RuntimeError(f"未找到评论 comment_id={comment_id} user_id={user_id}")

        logger.info("滚动到评论位置")
        await comment_el.scroll_into_view_if_needed()
        await asyncio.sleep(1)

        reply_btn = await comment_el.query_selector(".right .interactions .reply")
        if reply_btn is None:
            raise RuntimeError("无法找到回复按钮")
        await reply_btn.click()
        await asyncio.sleep(1)

        inp = await self.page.query_selector("div.input-box div.content-edit p.content-input")
        if inp is None:
            raise RuntimeError("无法找到回复输入框")
        await inp.fill(content)
        await asyncio.sleep(0.5)

        submit = await self.page.query_selector("div.bottom button.submit")
        if submit is None:
            raise RuntimeError("无法找到提交按钮")
        await submit.click()
        await asyncio.sleep(2)
        logger.info("回复评论成功")


async def _find_comment_element(page: Page, comment_id: str, user_id: str):
    """滚动查找指定评论元素"""
    logger.info(f"开始查找评论 comment_id={comment_id} user_id={user_id}")

    max_attempts = 100
    scroll_interval = 0.8

    await _scroll_to_comments_area(page)
    await asyncio.sleep(1)

    last_count = 0
    stagnant = 0

    for attempt in range(max_attempts):
        logger.debug(f"=== 查找尝试 {attempt + 1}/{max_attempts} ===")

        if await _check_end_container(page):
            logger.info("已到达评论底部，未找到目标评论")
            break

        current_count = await _get_comment_count(page)
        if current_count != last_count:
            last_count = current_count
            stagnant = 0
        else:
            stagnant += 1

        if stagnant >= 10:
            logger.info("评论数量停滞超过10次，停止查找")
            break

        # 滚动到最后一条评论触发懒加载
        if current_count > 0:
            elements = await page.query_selector_all(".parent-comment, .comment-item, .comment")
            if elements:
                await elements[-1].scroll_into_view_if_needed()
            await asyncio.sleep(0.3)

        # 继续向下滚动
        await page.evaluate("() => { window.scrollBy(0, window.innerHeight * 0.8); }")
        await asyncio.sleep(0.5)

        # 通过 comment_id 查找
        if comment_id:
            selector = f"#comment-{comment_id}"
            try:
                el = await page.wait_for_selector(selector, timeout=2_000)
                if el:
                    logger.info(f"通过 comment_id 找到评论: {comment_id}")
                    return el
            except Exception:
                pass

        # 通过 user_id 查找
        if user_id:
            try:
                elements = await page.query_selector_all(".comment-item, .comment, .parent-comment")
                for el in elements:
                    try:
                        user_el = await el.query_selector(f'[data-user-id="{user_id}"]')
                        if user_el:
                            logger.info(f"通过 user_id 找到评论: {user_id}")
                            return el
                    except Exception:
                        pass
            except Exception:
                pass

        await asyncio.sleep(scroll_interval)

    return None

