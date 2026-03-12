"""点赞与收藏功能，对应 Go 版本的 xiaohongshu/like_favorite.go"""

from __future__ import annotations

import asyncio
import json

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.feed_detail import _check_page_accessible, _make_feed_detail_url

SELECTOR_LIKE = ".interact-container .left .like-lottie"
SELECTOR_COLLECT = ".interact-container .left .reds-icon.collect-icon"


async def _get_interact_state(page: Page, feed_id: str) -> tuple[bool, bool]:
    """从 __INITIAL_STATE__ 读取点赞/收藏状态，返回 (liked, collected)"""
    result: str = await page.evaluate("""
        () => {
            if (window.__INITIAL_STATE__ &&
                window.__INITIAL_STATE__.note &&
                window.__INITIAL_STATE__.note.noteDetailMap) {
                return JSON.stringify(window.__INITIAL_STATE__.note.noteDetailMap);
            }
            return "";
        }
    """)
    if not result:
        raise ValueError("noteDetailMap not found")

    note_map: dict = json.loads(result)
    detail = note_map.get(feed_id)
    if detail is None:
        raise ValueError(f"feed {feed_id} not in noteDetailMap")

    interact = detail.get("note", {}).get("interactInfo", {})
    return interact.get("liked", False), interact.get("collected", False)


async def _prepare_page(page: Page, feed_id: str, xsec_token: str) -> None:
    url = _make_feed_detail_url(feed_id, xsec_token)
    logger.info(f"Opening feed detail page: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)
    await _check_page_accessible(page)


class LikeAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def like(self, feed_id: str, xsec_token: str) -> None:
        await self._perform(feed_id, xsec_token, target_liked=True)

    async def unlike(self, feed_id: str, xsec_token: str) -> None:
        await self._perform(feed_id, xsec_token, target_liked=False)

    async def _perform(self, feed_id: str, xsec_token: str, target_liked: bool) -> None:
        await _prepare_page(self.page, feed_id, xsec_token)

        try:
            liked, _ = await _get_interact_state(self.page, feed_id)
            if target_liked and liked:
                logger.info(f"feed {feed_id} already liked, skip")
                return
            if not target_liked and not liked:
                logger.info(f"feed {feed_id} not liked, skip unlike")
                return
        except Exception as e:
            logger.warning(f"failed to read interact state: {e}, try clicking anyway")

        await self._toggle(feed_id, target_liked)

    async def _toggle(self, feed_id: str, target_liked: bool) -> None:
        btn = await self.page.query_selector(SELECTOR_LIKE)
        if btn:
            await btn.click()
        await asyncio.sleep(3)

        try:
            liked, _ = await _get_interact_state(self.page, feed_id)
            if liked == target_liked:
                action = "点赞" if target_liked else "取消点赞"
                logger.info(f"feed {feed_id} {action}成功")
                return
        except Exception as e:
            logger.warning(f"验证点赞状态失败: {e}")
            return

        # 再试一次
        logger.warning(f"feed {feed_id} 状态未变化，再次点击")
        btn = await self.page.query_selector(SELECTOR_LIKE)
        if btn:
            await btn.click()
        await asyncio.sleep(2)


class FavoriteAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def favorite(self, feed_id: str, xsec_token: str) -> None:
        await self._perform(feed_id, xsec_token, target_collected=True)

    async def unfavorite(self, feed_id: str, xsec_token: str) -> None:
        await self._perform(feed_id, xsec_token, target_collected=False)

    async def _perform(self, feed_id: str, xsec_token: str, target_collected: bool) -> None:
        await _prepare_page(self.page, feed_id, xsec_token)

        try:
            _, collected = await _get_interact_state(self.page, feed_id)
            if target_collected and collected:
                logger.info(f"feed {feed_id} already collected, skip")
                return
            if not target_collected and not collected:
                logger.info(f"feed {feed_id} not collected, skip unfavorite")
                return
        except Exception as e:
            logger.warning(f"failed to read interact state: {e}, try clicking anyway")

        await self._toggle(feed_id, target_collected)

    async def _toggle(self, feed_id: str, target_collected: bool) -> None:
        btn = await self.page.query_selector(SELECTOR_COLLECT)
        if btn:
            await btn.click()
        await asyncio.sleep(3)

        try:
            _, collected = await _get_interact_state(self.page, feed_id)
            if collected == target_collected:
                action = "收藏" if target_collected else "取消收藏"
                logger.info(f"feed {feed_id} {action}成功")
                return
        except Exception as e:
            logger.warning(f"验证收藏状态失败: {e}")
            return

        # 再试一次
        logger.warning(f"feed {feed_id} 收藏状态未变化，再次点击")
        btn = await self.page.query_selector(SELECTOR_COLLECT)
        if btn:
            await btn.click()
        await asyncio.sleep(2)

