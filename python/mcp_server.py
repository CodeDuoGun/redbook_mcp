"""MCP 服务器：工具注册 + 处理器，对应 Go 版本的 mcp_server.go + mcp_handlers.go"""

from __future__ import annotations

import json
import traceback
from typing import Any

from loguru import logger
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types as mcp_types

from service import (
    FeedsListResponse,
    PublishRequest,
    PublishVideoRequest,
    XiaohongshuService,
)
from xiaohongshu.search import FilterOption
from xiaohongshu.types import CommentLoadConfig


# ==================== MCP Server 初始化 ====================

app = Server("xiaohongshu-mcp")
_svc = XiaohongshuService()


# ==================== 工具列表 ====================

@app.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="check_login_status",
            description="检查小红书登录状态",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="get_login_qrcode",
            description="获取登录二维码（返回 Base64 图片和超时时间）",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="delete_cookies",
            description="删除 cookies 文件，重置登录状态。删除后需要重新登录。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="publish_content",
            description="发布小红书图文内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "内容标题（最多20个字）"},
                    "content": {"type": "string", "description": "正文内容"},
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "图片路径列表（至少1张，支持 HTTP 链接或本地路径）",
                    },
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "话题标签列表"},
                    "schedule_at": {"type": "string", "description": "定时发布时间 ISO8601，如 2024-01-20T10:30:00+08:00"},
                    "is_original": {"type": "boolean", "description": "是否声明原创"},
                    "visibility": {"type": "string", "description": "可见范围：公开可见/仅自己可见/仅互关好友可见"},
                    "products": {"type": "array", "items": {"type": "string"}, "description": "商品关键词列表"},
                },
                "required": ["title", "content", "images"],
            },
        ),
        mcp_types.Tool(
            name="publish_with_video",
            description="发布小红书视频内容（仅支持本地单个视频文件）",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "内容标题（最多20个字）"},
                    "content": {"type": "string", "description": "正文内容"},
                    "video": {"type": "string", "description": "本地视频绝对路径"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "话题标签列表"},
                    "schedule_at": {"type": "string", "description": "定时发布时间 ISO8601"},
                    "visibility": {"type": "string", "description": "可见范围"},
                    "products": {"type": "array", "items": {"type": "string"}, "description": "商品关键词列表"},
                },
                "required": ["title", "content", "video"],
            },
        ),
        mcp_types.Tool(
            name="list_feeds",
            description="获取首页 Feeds 列表",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        mcp_types.Tool(
            name="search_feeds",
            description="搜索小红书内容（需要已登录）",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "filters": {
                        "type": "object",
                        "description": "筛选选项",
                        "properties": {
                            "sort_by": {"type": "string", "description": "排序：综合|最新|最多点赞|最多评论|最多收藏"},
                            "note_type": {"type": "string", "description": "笔记类型：不限|视频|图文"},
                            "publish_time": {"type": "string", "description": "发布时间：不限|一天内|一周内|半年内"},
                            "search_scope": {"type": "string", "description": "搜索范围：不限|已看过|未看过|已关注"},
                            "location": {"type": "string", "description": "位置：不限|同城|附近"},
                        },
                    },
                },
                "required": ["keyword"],
            },
        ),
        mcp_types.Tool(
            name="get_feed_detail",
            description="获取小红书笔记详情，返回内容、图片、作者、互动数据及评论列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {"type": "string", "description": "小红书笔记ID"},
                    "xsec_token": {"type": "string", "description": "访问令牌"},
                    "load_all_comments": {"type": "boolean", "description": "是否加载全部评论"},
                    "limit": {"type": "integer", "description": "最大评论数，默认20"},
                    "click_more_replies": {"type": "boolean", "description": "是否展开二级回复"},
                    "reply_limit": {"type": "integer", "description": "跳过回复数超过此值的评论，默认10"},
                    "scroll_speed": {"type": "string", "description": "滚动速度：slow|normal|fast"},
                },
                "required": ["feed_id", "xsec_token"],
            },
        ),
        mcp_types.Tool(
            name="user_profile",
            description="获取指定小红书用户主页，返回基本信息、关注粉丝数及笔记",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "小红书用户ID"},
                    "xsec_token": {"type": "string", "description": "访问令牌"},
                },
                "required": ["user_id", "xsec_token"],
            },
        ),
        mcp_types.Tool(
            name="post_comment_to_feed",
            description="发表评论到小红书笔记",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {"type": "string"},
                    "xsec_token": {"type": "string"},
                    "content": {"type": "string", "description": "评论内容"},
                },
                "required": ["feed_id", "xsec_token", "content"],
            },
        ),
        mcp_types.Tool(
            name="reply_comment_in_feed",
            description="回复小红书笔记下的指定评论",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {"type": "string"},
                    "xsec_token": {"type": "string"},
                    "comment_id": {"type": "string", "description": "目标评论ID"},
                    "user_id": {"type": "string", "description": "目标评论用户ID"},
                    "content": {"type": "string", "description": "回复内容"},
                },
                "required": ["feed_id", "xsec_token", "content"],
            },
        ),
        mcp_types.Tool(
            name="like_feed",
            description="为指定笔记点赞或取消点赞",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {"type": "string"},
                    "xsec_token": {"type": "string"},
                    "unlike": {"type": "boolean", "description": "true 为取消点赞"},
                },
                "required": ["feed_id", "xsec_token"],
            },
        ),
        mcp_types.Tool(
            name="favorite_feed",
            description="收藏指定笔记或取消收藏",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {"type": "string"},
                    "xsec_token": {"type": "string"},
                    "unfavorite": {"type": "boolean", "description": "true 为取消收藏"},
                },
                "required": ["feed_id", "xsec_token"],
            },
        ),
    ]


# ==================== 工具调用处理器 ====================

def _text(msg: str) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(type="text", text=msg)]


def _error(msg: str) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(type="text", text=msg)]


def _json(obj: Any) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(type="text", text=json.dumps(obj, ensure_ascii=False, indent=2))]


def _str_arg(args: dict, key: str, default: str = "") -> str:
    v = args.get(key, default)
    return str(v) if v is not None else default


def _bool_arg(args: dict, key: str, default: bool = False) -> bool:
    v = args.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _int_arg(args: dict, key: str, default: int = 0) -> int:
    v = args.get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _list_arg(args: dict, key: str) -> list[str]:
    v = args.get(key, [])
    if isinstance(v, list):
        return [str(i) for i in v]
    return []


@app.call_tool()
async def call_tool(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
    try:
        return await _dispatch(name, arguments or {})
    except Exception as e:
        logger.error(f"Tool {name} error: {e}\n{traceback.format_exc()}")
        return _error(f"工具 {name} 执行失败: {e}")


async def _dispatch(name: str, args: dict) -> list:
    if name == "check_login_status":
        return await _handle_check_login_status()
    if name == "get_login_qrcode":
        return await _handle_get_login_qrcode()
    if name == "delete_cookies":
        return await _handle_delete_cookies()
    if name == "publish_content":
        return await _handle_publish_content(args)
    if name == "publish_with_video":
        return await _handle_publish_video(args)
    if name == "list_feeds":
        return await _handle_list_feeds()
    if name == "search_feeds":
        return await _handle_search_feeds(args)
    if name == "get_feed_detail":
        return await _handle_get_feed_detail(args)
    if name == "user_profile":
        return await _handle_user_profile(args)
    if name == "post_comment_to_feed":
        return await _handle_post_comment(args)
    if name == "reply_comment_in_feed":
        return await _handle_reply_comment(args)
    if name == "like_feed":
        return await _handle_like_feed(args)
    if name == "favorite_feed":
        return await _handle_favorite_feed(args)
    return _error(f"未知工具: {name}")


# ==================== 各工具处理函数 ====================

async def _handle_check_login_status() -> list:
    logger.info("MCP: 检查登录状态")
    status = await _svc.check_login_status()
    if status.is_logged_in:
        text = f"✅ 已登录\n用户名: {status.username}\n\n你可以使用其他功能了。"
    else:
        text = "❌ 未登录\n\n请使用 get_login_qrcode 工具获取二维码进行登录。"
    return _text(text)


async def _handle_get_login_qrcode() -> list:
    logger.info("MCP: 获取登录扫码图片")
    from datetime import datetime, timedelta
    result = await _svc.get_login_qrcode()
    if result.is_logged_in:
        return _text("你当前已处于登录状态")

    try:
        sec = int(result.timeout.rstrip("s"))
        deadline = (datetime.now() + timedelta(seconds=sec)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        deadline = result.timeout

    contents: list = [mcp_types.TextContent(type="text", text=f"请用小红书 App 在 {deadline} 前扫码登录 👇")]
    if result.img:
        import base64
        img_data = result.img
        # 去掉 data:image/png;base64, 前缀
        if ";base64," in img_data:
            img_data = img_data.split(";base64,", 1)[1]
        contents.append(
            mcp_types.ImageContent(
                type="image",
                data=img_data,
                mimeType="image/png",
            )
        )
    return contents


async def _handle_delete_cookies() -> list:
    logger.info("MCP: 删除 cookies")
    from cookies import get_cookies_file_path
    await _svc.delete_cookies()
    path = get_cookies_file_path()
    return _text(f"Cookies 已成功删除，登录状态已重置。\n\n删除的文件路径: {path}\n\n下次操作时，需要重新登录。")


async def _handle_publish_content(args: dict) -> list:
    logger.info("MCP: 发布内容")
    req = PublishRequest(
        title=_str_arg(args, "title"),
        content=_str_arg(args, "content"),
        images=_list_arg(args, "images"),
        tags=_list_arg(args, "tags"),
        schedule_at=_str_arg(args, "schedule_at"),
        is_original=_bool_arg(args, "is_original"),
        visibility=_str_arg(args, "visibility"),
        products=_list_arg(args, "products"),
    )
    result = await _svc.publish_content(req)
    return _text(f"内容发布成功: {result}")


async def _handle_publish_video(args: dict) -> list:
    logger.info("MCP: 发布视频内容")
    video = _str_arg(args, "video")
    if not video:
        return _error("发布失败: 缺少本地视频文件路径")
    req = PublishVideoRequest(
        title=_str_arg(args, "title"),
        content=_str_arg(args, "content"),
        video=video,
        tags=_list_arg(args, "tags"),
        schedule_at=_str_arg(args, "schedule_at"),
        visibility=_str_arg(args, "visibility"),
        products=_list_arg(args, "products"),
    )
    result = await _svc.publish_video(req)
    return _text(f"视频发布成功: {result}")


async def _handle_list_feeds() -> list:
    logger.info("MCP: 获取 Feeds 列表")
    result = await _svc.list_feeds()
    return _json([f.model_dump() for f in result.feeds])


async def _handle_search_feeds(args: dict) -> list:
    logger.info("MCP: 搜索 Feeds")
    keyword = _str_arg(args, "keyword")
    if not keyword:
        return _error("搜索Feeds失败: 缺少关键词参数")
    filters_raw: dict = args.get("filters") or {}
    filters = FilterOption(
        sort_by=filters_raw.get("sort_by", ""),
        note_type=filters_raw.get("note_type", ""),
        publish_time=filters_raw.get("publish_time", ""),
        search_scope=filters_raw.get("search_scope", ""),
        location=filters_raw.get("location", ""),
    ) if filters_raw else None
    result = await _svc.search_feeds(keyword, filters)
    return _json([f.model_dump() for f in result.feeds])


async def _handle_get_feed_detail(args: dict) -> list:
    logger.info("MCP: 获取 Feed 详情")
    feed_id = _str_arg(args, "feed_id")
    xsec_token = _str_arg(args, "xsec_token")
    if not feed_id:
        return _error("获取Feed详情失败: 缺少feed_id参数")
    if not xsec_token:
        return _error("获取Feed详情失败: 缺少xsec_token参数")

    load_all = _bool_arg(args, "load_all_comments")
    config = CommentLoadConfig(
        click_more_replies=_bool_arg(args, "click_more_replies"),
        max_replies_threshold=_int_arg(args, "reply_limit", 10) or 10,
        max_comment_items=_int_arg(args, "limit", 20) or 20,
        scroll_speed=_str_arg(args, "scroll_speed", "normal") or "normal",
    )
    wrap = await _svc.get_feed_detail(feed_id, xsec_token, load_all, config)
    return _json(wrap.data.model_dump())


async def _handle_user_profile(args: dict) -> list:
    logger.info("MCP: 获取用户主页")
    user_id = _str_arg(args, "user_id")
    xsec_token = _str_arg(args, "xsec_token")
    if not user_id:
        return _error("获取用户主页失败: 缺少user_id参数")
    if not xsec_token:
        return _error("获取用户主页失败: 缺少xsec_token参数")
    result = await _svc.user_profile(user_id, xsec_token)
    return _json(result.model_dump())


async def _handle_post_comment(args: dict) -> list:
    logger.info("MCP: 发表评论")
    feed_id = _str_arg(args, "feed_id")
    xsec_token = _str_arg(args, "xsec_token")
    content = _str_arg(args, "content")
    if not feed_id:
        return _error("发表评论失败: 缺少feed_id参数")
    if not xsec_token:
        return _error("发表评论失败: 缺少xsec_token参数")
    if not content:
        return _error("发表评论失败: 缺少content参数")
    result = await _svc.post_comment_to_feed(feed_id, xsec_token, content)
    return _text(f"评论发表成功 - Feed ID: {result.feed_id}")


async def _handle_reply_comment(args: dict) -> list:
    logger.info("MCP: 回复评论")
    feed_id = _str_arg(args, "feed_id")
    xsec_token = _str_arg(args, "xsec_token")
    comment_id = _str_arg(args, "comment_id")
    user_id = _str_arg(args, "user_id")
    content = _str_arg(args, "content")
    if not feed_id:
        return _error("回复评论失败: 缺少feed_id参数")
    if not xsec_token:
        return _error("回复评论失败: 缺少xsec_token参数")
    if not comment_id and not user_id:
        return _error("回复评论失败: 缺少comment_id或user_id参数")
    if not content:
        return _error("回复评论失败: 缺少content参数")
    result = await _svc.reply_comment_to_feed(feed_id, xsec_token, comment_id, user_id, content)
    return _text(
        f"评论回复成功 - Feed ID: {result.feed_id}, "
        f"Comment ID: {result.target_comment_id}, User ID: {result.target_user_id}"
    )


async def _handle_like_feed(args: dict) -> list:
    feed_id = _str_arg(args, "feed_id")
    xsec_token = _str_arg(args, "xsec_token")
    unlike = _bool_arg(args, "unlike")
    if not feed_id:
        return _error("操作失败: 缺少feed_id参数")
    if not xsec_token:
        return _error("操作失败: 缺少xsec_token参数")
    if unlike:
        res = await _svc.unlike_feed(feed_id, xsec_token)
        return _text(f"取消点赞成功 - Feed ID: {res.feed_id}")
    else:
        res = await _svc.like_feed(feed_id, xsec_token)
        return _text(f"点赞成功 - Feed ID: {res.feed_id}")


async def _handle_favorite_feed(args: dict) -> list:
    feed_id = _str_arg(args, "feed_id")
    xsec_token = _str_arg(args, "xsec_token")
    unfavorite = _bool_arg(args, "unfavorite")
    if not feed_id:
        return _error("操作失败: 缺少feed_id参数")
    if not xsec_token:
        return _error("操作失败: 缺少xsec_token参数")
    if unfavorite:
        res = await _svc.unfavorite_feed(feed_id, xsec_token)
        return _text(f"取消收藏成功 - Feed ID: {res.feed_id}")
    else:
        res = await _svc.favorite_feed(feed_id, xsec_token)
        return _text(f"收藏成功 - Feed ID: {res.feed_id}")


# ==================== 运行入口 ====================

async def run_mcp_server() -> None:
    logger.info("xiaohongshu-mcp Python server starting (stdio)")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

