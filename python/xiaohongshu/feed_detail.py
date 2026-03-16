"""Feed 详情页（含评论滚动加载），对应 Go 版本的 xiaohongshu/feed_detail.go"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from xiaohongshu.types import (
    CommentList,
    CommentLoadConfig,
    FeedDetail,
    FeedDetailResponse,
    default_comment_load_config,
)

# ==================== 常量 ====================
_DEFAULT_MAX_ATTEMPTS = 500
_STAGNANT_LIMIT = 20
_MIN_SCROLL_DELTA = 10
_MAX_CLICK_PER_ROUND = 3
_LARGE_SCROLL_TRIGGER = 5
_BUTTON_CLICK_INTERVAL = 3
_FINAL_SPRINT_PUSH = 15


def _make_feed_detail_url(feed_id: str, xsec_token: str) -> str:
    return (
        f"https://www.xiaohongshu.com/explore/{feed_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_feed"
    )


# ==================== 辅助函数 ====================

def _sleep_random(min_ms: int, max_ms: int) -> float:
    """返回随机等待秒数（不执行 sleep，供 await asyncio.sleep 使用）"""
    if max_ms <= min_ms:
        return min_ms / 1000
    return (min_ms + random.randint(0, max_ms - min_ms)) / 1000


def _get_scroll_interval(speed: str) -> float:
    if speed == "slow":
        return (1200 + random.randint(0, 300)) / 1000
    if speed == "fast":
        return (300 + random.randint(0, 100)) / 1000
    return (600 + random.randint(0, 200)) / 1000


async def _get_scroll_top(page: Page) -> int:
    try:
        val = await page.evaluate(
            "() => window.pageYOffset || document.documentElement.scrollTop || 0"
        )
        return int(val)
    except Exception:
        return 0


async def _get_comment_count(page: Page) -> int:
    try:
        elements = await page.query_selector_all(".parent-comment")
        return len(elements)
    except Exception:
        return 0


async def _check_end_container(page: Page) -> bool:
    try:
        el = await page.query_selector(".end-container")
        if el is None:
            return False
        text = (await el.text_content() or "").strip().upper()
        return "THE END" in text or "THEEND" in text
    except Exception:
        return False


async def _check_no_comments(page: Page) -> bool:
    try:
        el = await page.query_selector(".no-comments-text")
        if el is None:
            return False
        text = (await el.text_content() or "").strip()
        return "这是一片荒地" in text
    except Exception:
        return False


async def _check_page_accessible(page: Page) -> None:
    """检测页面是否可访问，不可访问则抛出 RuntimeError"""
    await asyncio.sleep(0.5)
    try:
        wrapper = await page.query_selector(
            ".access-wrapper, .error-wrapper, .not-found-wrapper, .blocked-wrapper"
        )
        if wrapper is None:
            return
        text = (await wrapper.text_content() or "").strip()
        if not text:
            return
        keywords = [
            "当前笔记暂时无法浏览", "该内容因违规已被删除", "该笔记已被删除",
            "内容不存在", "笔记不存在", "已失效", "私密笔记",
            "仅作者可见", "因用户设置，你无法查看", "因违规无法查看",
        ]
        for kw in keywords:
            if kw in text:
                raise RuntimeError(f"笔记不可访问: {kw}")
        raise RuntimeError(f"笔记不可访问: {text}")
    except RuntimeError:
        raise
    except Exception:
        pass


async def _scroll_to_comments_area(page: Page) -> None:
    try:
        el = await page.query_selector(".comments-container")
        if el:
            await el.scroll_into_view_if_needed()
    except Exception:
        pass
    await asyncio.sleep(0.5)
    # 触发小滚动激活懒加载
    await page.evaluate("""
        (delta) => {
            let target = document.querySelector('.note-scroller')
                || document.querySelector('.interaction-container')
                || document.documentElement;
            target.dispatchEvent(new WheelEvent('wheel', {
                deltaY: delta, deltaMode: 0, bubbles: true, cancelable: true, view: window
            }));
        }
    """, 100)


async def _scroll_to_last_comment(page: Page) -> None:
    try:
        elements = await page.query_selector_all(".parent-comment")
        if elements:
            await elements[-1].scroll_into_view_if_needed()
    except Exception:
        pass


async def _human_scroll(page: Page, speed: str, large_mode: bool, push_count: int) -> tuple[bool, int, int]:
    """模拟人类滚动，返回 (scrolled, actual_delta, current_scroll_top)"""
    before_top = await _get_scroll_top(page)
    viewport_height: int = await page.evaluate("() => window.innerHeight")

    ratio_map = {"slow": 0.5, "fast": 0.9}
    base_ratio = ratio_map.get(speed, 0.7)
    if large_mode:
        base_ratio *= 2.0

    scrolled = False
    actual_delta = 0
    current_top = before_top
    prev_top = before_top

    for i in range(max(1, push_count)):
        delta = viewport_height * (base_ratio + random.random() * 0.2)
        delta = max(400.0, delta) + random.randint(-50, 50)
        await page.evaluate("(d) => { window.scrollBy(0, d); }", delta)
        await asyncio.sleep(_sleep_random(100, 200))

        current_top = await _get_scroll_top(page)
        step_delta = current_top - prev_top
        actual_delta += step_delta
        if step_delta > 5:
            scrolled = True
        prev_top = current_top

        if i < push_count - 1:
            await asyncio.sleep(_sleep_random(300, 700))

    if not scrolled and push_count > 0:
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(_sleep_random(300, 500))
        current_top = await _get_scroll_top(page)
        actual_delta = current_top - before_top
        scrolled = actual_delta > 5

    return scrolled, actual_delta, current_top


async def _click_show_more_buttons(page: Page, max_replies_threshold: int) -> tuple[int, int]:
    """点击展开更多回复按钮，返回 (clicked, skipped)"""
    clicked = skipped = 0
    try:
        elements = await page.query_selector_all(".show-more")
    except Exception:
        return 0, 0

    regex = re.compile(r"展开\s*(\d+)\s*条回复")
    max_click = _MAX_CLICK_PER_ROUND + random.randint(0, _MAX_CLICK_PER_ROUND)
    clicked_in_round = 0

    for el in elements:
        if clicked_in_round >= max_click:
            break
        try:
            visible = await el.is_visible()
            if not visible:
                continue
            box = await el.bounding_box()
            if not box:
                continue
            text = (await el.text_content() or "").strip()

            if max_replies_threshold > 0:
                m = regex.search(text)
                if m:
                    count = int(m.group(1))
                    if count > max_replies_threshold:
                        skipped += 1
                        continue

            await el.scroll_into_view_if_needed()
            await asyncio.sleep(_sleep_random(300, 800))
            await el.click()
            await asyncio.sleep(_sleep_random(500, 1200))
            clicked += 1
            clicked_in_round += 1
        except Exception as e:
            logger.debug(f"click show-more failed: {e}")

    return clicked, skipped


# ==================== 评论加载器 ====================

class _CommentLoader:
    def __init__(self, page: Page, config: CommentLoadConfig) -> None:
        self.page = page
        self.config = config
        self.total_clicked = 0
        self.total_skipped = 0
        self.attempts = 0
        self.last_count = 0
        self.last_scroll_top = 0
        self.stagnant_checks = 0

    def _calc_max_attempts(self) -> int:
        if self.config.max_comment_items > 0:
            return self.config.max_comment_items * 3
        return _DEFAULT_MAX_ATTEMPTS

    async def load(self) -> None:
        max_attempts = self._calc_max_attempts()
        scroll_interval = _get_scroll_interval(self.config.scroll_speed)

        logger.info("开始加载评论...")
        await _scroll_to_comments_area(self.page)
        await asyncio.sleep(_sleep_random(300, 700))

        if await _check_no_comments(self.page):
            logger.info("检测到无评论区域，跳过加载")
            return

        for self.attempts in range(max_attempts):
            logger.debug(f"=== 尝试 {self.attempts + 1}/{max_attempts} ===")

            if await _check_end_container(self.page):
                current = await _get_comment_count(self.page)
                logger.info(f"检测到 THE END，加载完成: {current} 条评论")
                return

            # 点击更多按钮
            if self.config.click_more_replies and self.attempts % _BUTTON_CLICK_INTERVAL == 0:
                c, s = await _click_show_more_buttons(self.page, self.config.max_replies_threshold)
                if c > 0 or s > 0:
                    self.total_clicked += c
                    self.total_skipped += s
                    await asyncio.sleep(_sleep_random(500, 1200))
                    c2, s2 = await _click_show_more_buttons(self.page, self.config.max_replies_threshold)
                    self.total_clicked += c2
                    self.total_skipped += s2

            current_count = await _get_comment_count(self.page)

            # 更新停滞检测
            if current_count != self.last_count:
                logger.info(f"评论增加: {self.last_count} -> {current_count}")
                self.last_count = current_count
                self.stagnant_checks = 0
            else:
                self.stagnant_checks += 1

            # 目标数量检查
            if self.config.max_comment_items > 0 and current_count >= self.config.max_comment_items:
                logger.info(f"已达到目标评论数: {current_count}/{self.config.max_comment_items}")
                return

            # 滚动
            if current_count > 0:
                await _scroll_to_last_comment(self.page)
                await asyncio.sleep(_sleep_random(300, 500))

            large_mode = self.stagnant_checks >= _LARGE_SCROLL_TRIGGER
            push_count = (3 + random.randint(0, 3)) if large_mode else 1
            _, scroll_delta, current_top = await _human_scroll(
                self.page, self.config.scroll_speed, large_mode, push_count
            )

            if scroll_delta < _MIN_SCROLL_DELTA or current_top == self.last_scroll_top:
                self.stagnant_checks += 1
            else:
                self.stagnant_checks = 0
                self.last_scroll_top = current_top

            # 停滞过多 -> 大冲刺
            if self.stagnant_checks >= _STAGNANT_LIMIT:
                logger.info("停滞过多，触发大冲刺")
                await _human_scroll(self.page, self.config.scroll_speed, True, 10)
                self.stagnant_checks = 0

            await asyncio.sleep(scroll_interval)

        # 最终冲刺
        logger.info("达到最大尝试次数，最后冲刺")
        await _human_scroll(self.page, self.config.scroll_speed, True, _FINAL_SPRINT_PUSH)


# ==================== 主 Action ====================

class FeedDetailAction:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def get_feed_detail_with_config(
        self,
        feed_id: str,
        xsec_token: str,
        load_all_comments: bool,
        config: CommentLoadConfig,
    ) -> FeedDetailResponse:
        url = _make_feed_detail_url(feed_id, xsec_token)
        logger.info(f"打开 feed 详情页: {url}")

        for attempt in range(3):
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                await self.page.wait_for_load_state("networkidle")
                break
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"页面导航失败: {e}") from e
                await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        await _check_page_accessible(self.page)

        if load_all_comments:
            loader = _CommentLoader(self.page, config)
            try:
                await loader.load()
            except Exception as e:
                logger.warning(f"加载全部评论失败: {e}")

        return await self._extract_feed_detail(feed_id)

    async def get_feed_detail(
        self,
        feed_id: str,
        xsec_token: str,
        load_all_comments: bool,
        config: Optional[CommentLoadConfig] = None,
    ) -> FeedDetailResponse:
        if config is None:
            config = default_comment_load_config()
        return await self.get_feed_detail_with_config(feed_id, xsec_token, load_all_comments, config)

    async def _extract_feed_detail(self, feed_id: str) -> FeedDetailResponse:
        result: str = ""
        for _ in range(3):
            result = await self.page.evaluate("""
                () => {
                    if (window.__INITIAL_STATE__ &&
                        window.__INITIAL_STATE__.note &&
                        window.__INITIAL_STATE__.note.noteDetailMap) {
                        return JSON.stringify(window.__INITIAL_STATE__.note.noteDetailMap);
                    }
                    return "";
                }
            """)
            if result:
                break
            await asyncio.sleep(0.2)

        if not result:
            raise ValueError(f"feed detail not found in __INITIAL_STATE__ for {feed_id}")

        note_detail_map: dict = json.loads(result)
        with open("result.json", "w") as f:
            f.write(json.dumps(json.loads(result), ensure_ascii=False, indent=2))
        detail = note_detail_map.get(feed_id)
        logger.info(f"detail: {detail.keys() if isinstance(detail, dict) else type(detail)}")
        if detail is None:
            raise ValueError(f"feed {feed_id} not found in noteDetailMap")
        return FeedDetailResponse(
            note=FeedDetail.model_validate(detail.get("note", {})),
            comments=CommentList.model_validate(detail.get("comments", {})),
        )

