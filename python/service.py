"""业务编排层，对应 Go 版本的 service.go"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from browser import BrowserSession, new_browser_session
from cookies import new_cookie_manager
from xiaohongshu.comment_feed import CommentFeedAction
from xiaohongshu.feed_detail import FeedDetailAction
from xiaohongshu.feeds import FeedsListAction
from xiaohongshu.like_favorite import FavoriteAction, LikeAction
from xiaohongshu.login import LoginAction
from xiaohongshu.publish import PublishAction, PublishImageContent
from xiaohongshu.publish_video import PublishVideoAction, PublishVideoContent
from xiaohongshu.search import FilterOption, SearchAction
from xiaohongshu.types import (
    ActionResult,
    CommentLoadConfig,
    Feed,
    FeedDetailResponse,
    PostCommentResponse,
    ReplyCommentResponse,
    UserProfileResponse,
    default_comment_load_config,
)
from xiaohongshu.user_profile import UserProfileAction


# ==================== Request / Response 数据类 ====================

@dataclass
class LoginStatusResponse:
    is_logged_in: bool
    username: str = ""


@dataclass
class LoginQrcodeResponse:
    timeout: str
    is_logged_in: bool
    img: str = ""


@dataclass
class PublishRequest:
    title: str
    content: str
    images: list[str]
    tags: list[str] = field(default_factory=list)
    schedule_at: str = ""
    is_original: bool = False
    visibility: str = ""
    products: list[str] = field(default_factory=list)


@dataclass
class PublishVideoRequest:
    title: str
    content: str
    video: str
    tags: list[str] = field(default_factory=list)
    schedule_at: str = ""
    visibility: str = ""
    products: list[str] = field(default_factory=list)


@dataclass
class PublishResponse:
    title: str
    content: str
    images: int
    status: str
    post_id: str = ""


@dataclass
class PublishVideoResponse:
    title: str
    content: str
    video: str
    status: str
    post_id: str = ""


@dataclass
class FeedsListResponse:
    feeds: list[Feed]
    count: int


@dataclass
class FeedDetailWrap:
    feed_id: str
    data: FeedDetailResponse


# ==================== 工具函数 ====================

def _parse_schedule_at(schedule_at: str) -> Optional[datetime]:
    """解析 ISO8601 定时发布时间，验证范围 1h ~ 14d"""
    if not schedule_at:
        return None
    try:
        t = datetime.fromisoformat(schedule_at)
    except ValueError as e:
        raise ValueError(f"定时发布时间格式错误，请使用 ISO8601 格式: {e}") from e

    now = datetime.now(tz=t.tzinfo or timezone.utc)
    from datetime import timedelta
    min_t = now + timedelta(hours=1)
    max_t = now + timedelta(days=14)

    if t < min_t:
        raise ValueError(
            f"定时发布时间必须至少在1小时后，当前设置: {t.strftime('%Y-%m-%d %H:%M')}，"
            f"最早可选: {min_t.strftime('%Y-%m-%d %H:%M')}"
        )
    if t > max_t:
        raise ValueError(
            f"定时发布时间不能超过14天，当前设置: {t.strftime('%Y-%m-%d %H:%M')}，"
            f"最晚可选: {max_t.strftime('%Y-%m-%d %H:%M')}"
        )
    return t


def _calc_title_length(title: str) -> int:
    """简单计算标题长度（每个中文字算1，与 Go 版本 xhsutil.CalcTitleLength 对应）"""
    # 小红书限制：中英文混合，最多20个字（中文1字，英文单词1字）
    # 简化处理：直接用字符数
    return len(title)


async def _process_images(images: list[str]) -> list[str]:
    """处理图片列表：下载 HTTP 图片到临时目录，本地路径直接使用"""
    import tempfile
    import urllib.request

    result: list[str] = []
    for img in images:
        if img.startswith("http://") or img.startswith("https://"):
            suffix = ".jpg"
            for ext in [".png", ".gif", ".webp", ".jpeg"]:
                if ext in img.lower():
                    suffix = ext
                    break
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.close()
            try:
                urllib.request.urlretrieve(img, tmp.name)
                result.append(tmp.name)
                logger.info(f"下载图片成功: {img} -> {tmp.name}")
            except Exception as e:
                logger.warning(f"下载图片失败: {img}: {e}")
        else:
            if os.path.exists(img):
                result.append(img)
            else:
                logger.warning(f"图片文件不存在: {img}")
    return result


# ==================== 服务类 ====================

class XiaohongshuService:
    """小红书业务服务，每个方法独立创建浏览器会话"""

    async def delete_cookies(self) -> None:
        cm = new_cookie_manager()
        cm.delete_cookies()

    async def check_login_status(self) -> LoginStatusResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = LoginAction(page)
            logged_in = await action.check_login_status()
            username = os.getenv("XHS_USERNAME", "")
            return LoginStatusResponse(is_logged_in=logged_in, username=username)
        finally:
            await session.close()

    async def get_login_qrcode(self) -> LoginQrcodeResponse:
        """获取二维码，后台异步等待登录并保存 cookies"""
        import asyncio

        session = await new_browser_session()
        page = await session.new_page()
        action = LoginAction(page)

        img, logged_in = await action.fetch_qrcode_image()
        if logged_in:
            await session.close()
            return LoginQrcodeResponse(timeout="0s", is_logged_in=True)

        timeout_sec = 240.0

        async def _wait_and_save() -> None:
            try:
                success = await action.wait_for_login(timeout=timeout_sec)
                if success:
                    cookies = await session.get_cookies()
                    cm = new_cookie_manager()
                    cm.save_cookies(cookies)
                    logger.info("登录成功，cookies 已保存")
            except Exception as e:
                logger.error(f"等待登录失败: {e}")
            finally:
                await session.close()

        asyncio.create_task(_wait_and_save())

        return LoginQrcodeResponse(
            timeout=f"{int(timeout_sec)}s",
            is_logged_in=False,
            img=img,
        )

    async def publish_content(self, req: PublishRequest) -> PublishResponse:
        if _calc_title_length(req.title) > 20:
            raise ValueError("标题长度超过限制")
        image_paths = await _process_images(req.images)
        if not image_paths:
            raise ValueError("没有有效的图片文件")
        schedule_time = _parse_schedule_at(req.schedule_at)

        content = PublishImageContent(
            title=req.title,
            content=req.content,
            image_paths=image_paths,
            tags=req.tags,
            schedule_time=schedule_time,
            is_original=req.is_original,
            visibility=req.visibility,
            products=req.products,
        )

        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = await PublishAction.create_image_action(page)
            await action.publish(content)
        finally:
            await session.close()

        return PublishResponse(
            title=req.title,
            content=req.content,
            images=len(image_paths),
            status="发布完成",
        )

    async def publish_video(self, req: PublishVideoRequest) -> PublishVideoResponse:
        if _calc_title_length(req.title) > 20:
            raise ValueError("标题长度超过限制")
        if not req.video:
            raise ValueError("必须提供本地视频文件")
        if not os.path.exists(req.video):
            raise ValueError(f"视频文件不存在或不可访问: {req.video}")
        schedule_time = _parse_schedule_at(req.schedule_at)

        content = PublishVideoContent(
            title=req.title,
            content=req.content,
            video_path=req.video,
            tags=req.tags,
            schedule_time=schedule_time,
            visibility=req.visibility,
            products=req.products,
        )

        session = await new_browser_session()
        try:
            page = await session.new_page()
            publish_action = await PublishAction.create_video_action(page)
            video_action = PublishVideoAction(page)
            video_action._publish_action = publish_action
            await video_action.publish_video(content)
        finally:
            await session.close()

        return PublishVideoResponse(
            title=req.title,
            content=req.content,
            video=req.video,
            status="发布完成",
        )

    async def list_feeds(self) -> FeedsListResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = FeedsListAction(page)
            feeds = await action.get_feeds_list()
            return FeedsListResponse(feeds=feeds, count=len(feeds))
        finally:
            await session.close()

    async def search_feeds(
        self, keyword: str, filters: Optional[FilterOption] = None
    ) -> FeedsListResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = SearchAction(page)
            feeds = await action.search(keyword, filters)
            return FeedsListResponse(feeds=feeds, count=len(feeds))
        finally:
            await session.close()

    async def get_feed_detail(
        self,
        feed_id: str,
        xsec_token: str,
        load_all_comments: bool,
        config: Optional[CommentLoadConfig] = None,
    ) -> FeedDetailWrap:
        if config is None:
            config = default_comment_load_config()
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = FeedDetailAction(page)
            result = await action.get_feed_detail_with_config(
                feed_id, xsec_token, load_all_comments, config
            )
            return FeedDetailWrap(feed_id=feed_id, data=result)
        finally:
            await session.close()

    async def user_profile(self, user_id: str, xsec_token: str) -> UserProfileResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = UserProfileAction(page)
            return await action.user_profile(user_id, xsec_token)
        finally:
            await session.close()

    async def post_comment_to_feed(
        self, feed_id: str, xsec_token: str, content: str
    ) -> PostCommentResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = CommentFeedAction(page)
            await action.post_comment(feed_id, xsec_token, content)
            return PostCommentResponse(feed_id=feed_id, success=True, message="评论发表成功")
        finally:
            await session.close()

    async def reply_comment_to_feed(
        self,
        feed_id: str,
        xsec_token: str,
        comment_id: str,
        user_id: str,
        content: str,
    ) -> ReplyCommentResponse:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = CommentFeedAction(page)
            await action.reply_to_comment(feed_id, xsec_token, comment_id, user_id, content)
            return ReplyCommentResponse(
                feed_id=feed_id,
                target_comment_id=comment_id,
                target_user_id=user_id,
                success=True,
                message="评论回复成功",
            )
        finally:
            await session.close()

    async def like_feed(self, feed_id: str, xsec_token: str) -> ActionResult:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = LikeAction(page)
            await action.like(feed_id, xsec_token)
            return ActionResult(feed_id=feed_id, success=True, message="点赞成功或已点赞")
        finally:
            await session.close()

    async def unlike_feed(self, feed_id: str, xsec_token: str) -> ActionResult:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = LikeAction(page)
            await action.unlike(feed_id, xsec_token)
            return ActionResult(feed_id=feed_id, success=True, message="取消点赞成功或未点赞")
        finally:
            await session.close()

    async def favorite_feed(self, feed_id: str, xsec_token: str) -> ActionResult:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = FavoriteAction(page)
            await action.favorite(feed_id, xsec_token)
            return ActionResult(feed_id=feed_id, success=True, message="收藏成功或已收藏")
        finally:
            await session.close()

    async def unfavorite_feed(self, feed_id: str, xsec_token: str) -> ActionResult:
        session = await new_browser_session()
        try:
            page = await session.new_page()
            action = FavoriteAction(page)
            await action.unfavorite(feed_id, xsec_token)
            return ActionResult(feed_id=feed_id, success=True, message="取消收藏成功或未收藏")
        finally:
            await session.close()

