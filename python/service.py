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

    async def creative_inspiration(
        self,
        title: Optional[str] = None,
        content: Optional[str] = None,
        images: Optional[list[str]] = None,
        video: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> dict:
        """直接生成最多3套可发布的小红书内容方案（标题+文案+配图/视频建议），并自动以仅自己可见发布"""
        import base64
        import json as _json
        import mimetypes
        import httpx
        import yaml

        # ---------- 读取 API Key ----------
        api_key = os.getenv("BAILIAN_API_KEY", "")
        if not api_key:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.yaml",
            )
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                api_key = cfg.get("default", {}).get("BAILIAN_API_KEY", "")

        if not api_key:
            raise ValueError("未配置 BAILIAN_API_KEY，请在 config.yaml 或环境变量中设置")

        # ---------- 构造多模态消息 ----------
        user_parts: list[dict] = []

        ref_lines: list[str] = []
        if title:
            ref_lines.append(f"【标题】{title}")
        if content:
            ref_lines.append(f"【正文】{content}")
        if topic:
            ref_lines.append(f"【创作方向】{topic}")
        if video:
            ref_lines.append(f"【参考视频】{video}")
        if ref_lines:
            user_parts.append({"type": "text", "text": "\n".join(ref_lines)})
        else:
            user_parts.append({"type": "text", "text": "请根据图片内容结合当前小红书热门话题生成创作方案。"})

        # 图片（最多4张）
        if images:
            for img_src in images[:4]:
                try:
                    if img_src.startswith("http://") or img_src.startswith("https://"):
                        user_parts.append({"type": "image_url", "image_url": {"url": img_src}})
                    elif os.path.exists(img_src):
                        mime, _ = mimetypes.guess_type(img_src)
                        mime = mime or "image/jpeg"
                        with open(img_src, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        user_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        })
                except Exception as e:
                    logger.warning(f"跳过图片 {img_src}: {e}")

        has_video = bool(video)

        # ---------- 系统 Prompt：直接输出 JSON 方案，不输出中间分析 ----------
        system_prompt = (
            "你是一位资深小红书内容策划专家。"
            "根据用户提供的参考内容（标题、正文、图片、视频等），"
            "直接生成最多3套完整的小红书发布方案，无需输出分析过程。\n"
            "每套方案包含：\n"
            "  - title: 标题（不超过20字，含emoji，符合小红书爆款规律）\n"
            "  - content: 正文文案（150字以内，含2-3个#话题标签，语言活泼接地气）\n"
            "  - image_prompt: 配图拍摄/制作要点（一句话，具体可执行）\n"
        )
        if has_video:
            system_prompt += (
                "  - video_prompt: 视频拍摄要点（一句话，含时长/节奏/BGM风格建议）\n"
            )
        system_prompt += (
            "\n请严格以如下 JSON 格式输出，不要有任何其他文字：\n"
            '[{"title":"...","content":"...","image_prompt":"..."}]'
            if not has_video else
            '[{"title":"...","content":"...","image_prompt":"...","video_prompt":"..."}]'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_parts},
        ]

        # ---------- 调用百炼 API ----------
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "qwen-vl-max",
            "messages": messages,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw = "\n".join(part.get("text", "") for part in raw if isinstance(part, dict))

        # 尝试解析 JSON 方案列表
        plans: list[dict] = []
        try:
            # 提取第一个 JSON 数组
            import re as _re
            m = _re.search(r'\[\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*\]', raw, _re.S)
            if m:
                plans = _json.loads(m.group())
        except Exception as e:
            logger.warning(f"解析 AI 方案 JSON 失败，原始文本: {raw[:200]}... 错误: {e}")

        # 限制最多3套
        plans = plans[:3]

        # ---------- 自动发布每套方案（仅自己可见）----------
        publish_results: list[dict] = []
        ref_images = images or []

        for idx, plan in enumerate(plans):
            plan_title = str(plan.get("title", ""))[:20]
            plan_content = str(plan.get("content", ""))
            plan_image_prompt = str(plan.get("image_prompt", ""))
            plan_video_prompt = str(plan.get("video_prompt", "")) if has_video else ""

            pub_result: dict = {
                "index": idx + 1,
                "title": plan_title,
                "content": plan_content,
                "image_prompt": plan_image_prompt,
                "video_prompt": plan_video_prompt,
                "published": False,
                "post_id": "",
                "error": "",
            }

            try:
                if has_video and video:
                    # 发布视频
                    video_req = PublishVideoRequest(
                        title=plan_title,
                        content=plan_content,
                        video=video,
                        tags=[],
                        visibility="仅自己可见",
                    )
                    pub = await self.publish_video(video_req)
                    pub_result["published"] = True
                    pub_result["post_id"] = pub.post_id
                elif ref_images:
                    # 发布图文
                    image_req = PublishRequest(
                        title=plan_title,
                        content=plan_content,
                        images=ref_images,
                        tags=[],
                        visibility="仅自己可见",
                    )
                    pub = await self.publish_content(image_req)
                    pub_result["published"] = True
                    pub_result["post_id"] = pub.post_id
                else:
                    pub_result["error"] = "无可用图片或视频，跳过发布"
            except Exception as e:
                logger.warning(f"方案 {idx+1} 发布失败: {e}")
                pub_result["error"] = str(e)

            publish_results.append(pub_result)

        return {
            "plans": publish_results,
            "model": data.get("model", "qwen-vl-max"),
            "raw_ai_response": raw,
        }

