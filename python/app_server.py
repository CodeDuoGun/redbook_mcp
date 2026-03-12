import asyncio
import contextlib
import signal
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from mcp.server.fastmcp import FastMCP
from routes import setup_routes
from mcp_server import init_mcp_server
from cookies import get_cookies_file_path
from service import (
    PublishRequest,
    PublishVideoRequest,
    XiaohongshuService,
)
from xiaohongshu.search import FilterOption
from xiaohongshu.types import CommentLoadConfig, default_comment_load_config
import dataclasses

logger = logging.getLogger(__name__)


def _success(data, message: str = ""):
    return JSONResponse(content={"success": True, "data": data, "message": message})


def _error(status_code: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "code": code, "details": details},
    )


class AppServer:

    def __init__(self, xiaohongshu_service: XiaohongshuService):
        self.xiaohongshu_service = xiaohongshu_service

        # 初始化 MCP Server
        self.mcp_server: FastMCP = init_mcp_server(self)

        # HTTP server
        self.server: uvicorn.Server | None = None

        # FastAPI app — created with lifespan to manage MCP session manager
        @contextlib.asynccontextmanager
        async def lifespan(app: FastAPI):
            async with self.mcp_server.session_manager.run():
                yield

        self.app: FastAPI = FastAPI(lifespan=lifespan)

    def start(self, port: str):

        port = int(port)

        # 注册路由 (must happen after app creation, before serve)
        setup_routes(self)

        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )

        self.server = uvicorn.Server(config)

        logging.info(f"启动 HTTP 服务器: {port}")

        loop = asyncio.get_event_loop()

        # 注册信号处理
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.shutdown())
            )

        loop.run_until_complete(self.server.serve())

    async def shutdown(self):

        logging.info("正在关闭服务器...")

        if self.server:
            await self.server.shutdown()

        logging.info("服务器已优雅关闭")

    # -------------------------
    # HTTP API Handlers
    # -------------------------

    async def check_login_status_handler(self):
        try:
            status = await self.xiaohongshu_service.check_login_status()
            return _success(
                {"is_logged_in": status.is_logged_in, "username": status.username},
                "检查登录状态成功",
            )
        except Exception as e:
            return _error(500, "STATUS_CHECK_FAILED", "检查登录状态失败", str(e))

    async def get_login_qrcode_handler(self):
        try:
            result = await self.xiaohongshu_service.get_login_qrcode()
            return _success(
                {
                    "timeout": result.timeout,
                    "is_logged_in": result.is_logged_in,
                    "img": result.img,
                },
                "获取登录二维码成功",
            )
        except Exception as e:
            return _error(500, "STATUS_CHECK_FAILED", "获取登录二维码失败", str(e))

    async def delete_cookies_handler(self):
        try:
            await self.xiaohongshu_service.delete_cookies()
            cookie_path = get_cookies_file_path()
            return _success(
                {
                    "cookie_path": cookie_path,
                    "message": "Cookies 已成功删除，登录状态已重置。下次操作时需要重新登录。",
                },
                "删除 cookies 成功",
            )
        except Exception as e:
            return _error(500, "DELETE_COOKIES_FAILED", "删除 cookies 失败", str(e))

    async def publish_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            req = PublishRequest(
                title=body.get("title", ""),
                content=body.get("content", ""),
                images=body.get("images", []),
                tags=body.get("tags", []),
                schedule_at=body.get("schedule_at", ""),
                is_original=body.get("is_original", False),
                visibility=body.get("visibility", ""),
                products=body.get("products", []),
            )
            result = await self.xiaohongshu_service.publish_content(req)
            return _success(
                {
                    "title": result.title,
                    "content": result.content,
                    "images": result.images,
                    "status": result.status,
                    "post_id": result.post_id,
                },
                "发布成功",
            )
        except Exception as e:
            return _error(500, "PUBLISH_FAILED", "发布失败", str(e))

    async def publish_video_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            req = PublishVideoRequest(
                title=body.get("title", ""),
                content=body.get("content", ""),
                video=body.get("video", ""),
                tags=body.get("tags", []),
                schedule_at=body.get("schedule_at", ""),
                visibility=body.get("visibility", ""),
                products=body.get("products", []),
            )
            result = await self.xiaohongshu_service.publish_video(req)
            return _success(
                {
                    "title": result.title,
                    "content": result.content,
                    "video": result.video,
                    "status": result.status,
                    "post_id": result.post_id,
                },
                "视频发布成功",
            )
        except Exception as e:
            return _error(500, "PUBLISH_VIDEO_FAILED", "视频发布失败", str(e))

    async def list_feeds_handler(self):
        try:
            result = await self.xiaohongshu_service.list_feeds()
            import dataclasses
            return _success(
                {"feeds": [dataclasses.asdict(f) for f in result.feeds], "count": result.count},
                "获取Feeds列表成功",
            )
        except Exception as e:
            return _error(500, "LIST_FEEDS_FAILED", "获取Feeds列表失败", str(e))

    async def search_feeds_handler(self, request: Request):
        try:
            keyword = ""
            filters = None

            if request.method == "POST":
                body = await request.json()
                keyword = body.get("keyword", "")
                filters_data = body.get("filters")
                if filters_data:
                    filters = FilterOption(
                        sort_by=filters_data.get("sort_by", ""),
                        note_type=filters_data.get("note_type", ""),
                        publish_time=filters_data.get("publish_time", ""),
                        search_scope=filters_data.get("search_scope", ""),
                        location=filters_data.get("location", ""),
                    )
            else:
                keyword = request.query_params.get("keyword", "")

            if not keyword:
                return _error(400, "MISSING_KEYWORD", "缺少关键词参数", "keyword parameter is required")

            result = await self.xiaohongshu_service.search_feeds(keyword, filters)
            import dataclasses
            return _success(
                {"feeds": [dataclasses.asdict(f) for f in result.feeds], "count": result.count},
                "搜索Feeds成功",
            )
        except Exception as e:
            return _error(500, "SEARCH_FEEDS_FAILED", "搜索Feeds失败", str(e))

    async def get_feed_detail_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            feed_id = body.get("feed_id", "")
            xsec_token = body.get("xsec_token", "")
            load_all_comments = body.get("load_all_comments", False)

            comment_config_data = body.get("comment_config")
            config = None
            if comment_config_data:
                config = CommentLoadConfig(
                    click_more_replies=comment_config_data.get("click_more_replies", False),
                    max_replies_threshold=comment_config_data.get("max_replies_threshold", 10),
                    max_comment_items=comment_config_data.get("max_comment_items", 20),
                    scroll_speed=comment_config_data.get("scroll_speed", ""),
                )

            result = await self.xiaohongshu_service.get_feed_detail(
                feed_id, xsec_token, load_all_comments, config
            )
            import dataclasses
            return _success(
                {"feed_id": result.feed_id, "data": dataclasses.asdict(result.data)},
                "获取Feed详情成功",
            )
        except Exception as e:
            return _error(500, "GET_FEED_DETAIL_FAILED", "获取Feed详情失败", str(e))

    async def user_profile_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            user_id = body.get("user_id", "")
            xsec_token = body.get("xsec_token", "")
            result = await self.xiaohongshu_service.user_profile(user_id, xsec_token)
            import dataclasses
            return _success({"data": dataclasses.asdict(result)}, "获取用户主页成功")
        except Exception as e:
            return _error(500, "GET_USER_PROFILE_FAILED", "获取用户主页失败", str(e))

    async def post_comment_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            feed_id = body.get("feed_id", "")
            xsec_token = body.get("xsec_token", "")
            content = body.get("content", "")
            result = await self.xiaohongshu_service.post_comment_to_feed(feed_id, xsec_token, content)
            import dataclasses
            return _success(dataclasses.asdict(result), result.message)
        except Exception as e:
            return _error(500, "POST_COMMENT_FAILED", "发表评论失败", str(e))

    async def reply_comment_handler(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error(400, "INVALID_REQUEST", "请求参数错误", "invalid JSON body")

        try:
            feed_id = body.get("feed_id", "")
            xsec_token = body.get("xsec_token", "")
            comment_id = body.get("comment_id", "")
            user_id = body.get("user_id", "")
            content = body.get("content", "")
            result = await self.xiaohongshu_service.reply_comment_to_feed(
                feed_id, xsec_token, comment_id, user_id, content
            )
            import dataclasses
            return _success(dataclasses.asdict(result), result.message)
        except Exception as e:
            return _error(500, "REPLY_COMMENT_FAILED", "回复评论失败", str(e))

    async def my_profile_handler(self):
        try:
            result = await self.xiaohongshu_service.check_login_status()
            return _success(
                {"data": {"is_logged_in": result.is_logged_in, "username": result.username}},
                "获取我的主页成功",
            )
        except Exception as e:
            return _error(500, "GET_MY_PROFILE_FAILED", "获取我的主页失败", str(e))

    # -------------------------
    # MCP Tool Handlers (called from mcp_server.py)
    # -------------------------

    async def handle_check_login_status(self, ctx):
        status = await self.xiaohongshu_service.check_login_status()
        text = f"登录状态: {'已登录' if status.is_logged_in else '未登录'}"
        if status.username:
            text += f"\n用户名: {status.username}"
        return {"content": [{"type": "text", "text": text}], "is_error": False}

    async def handle_get_login_qrcode(self, ctx):
        result = await self.xiaohongshu_service.get_login_qrcode()
        if result.is_logged_in:
            return {"content": [{"type": "text", "text": "已登录，无需扫码"}], "is_error": False}
        contents = [
            {"type": "text", "text": f"请扫描二维码登录（{result.timeout} 内有效）"},
        ]
        if result.img:
            contents.append({"type": "image", "data": result.img, "mime_type": "image/png"})
        return {"content": contents, "is_error": False}

    async def handle_delete_cookies(self, ctx):
        await self.xiaohongshu_service.delete_cookies()
        cookie_path = get_cookies_file_path()
        return {
            "content": [{"type": "text", "text": f"Cookies 已删除（{cookie_path}），请重新登录"}],
            "is_error": False,
        }

    async def handle_publish_content(self, ctx, args_map):
        req = PublishRequest(
            title=args_map.get("title", ""),
            content=args_map.get("content", ""),
            images=args_map.get("images", []),
            tags=args_map.get("tags", []),
            schedule_at=args_map.get("schedule_at", ""),
            is_original=args_map.get("is_original", False),
            visibility=args_map.get("visibility", ""),
            products=args_map.get("products", []),
        )
        result = await self.xiaohongshu_service.publish_content(req)
        return {
            "content": [{"type": "text", "text": f"发布成功\n标题: {result.title}\n状态: {result.status}"}],
            "is_error": False,
        }

    async def handle_search_feeds(self, ctx, args):
        filters = None
        if hasattr(args, "filters") and args.filters:
            f = args.filters
            filters = FilterOption(
                sort_by=getattr(f, "sort_by", ""),
                note_type=getattr(f, "note_type", ""),
                publish_time=getattr(f, "publish_time", ""),
                search_scope=getattr(f, "search_scope", ""),
                location=getattr(f, "location", ""),
            )
        result = await self.xiaohongshu_service.search_feeds(args.keyword, filters)
        import json, dataclasses
        text = json.dumps(
            {"count": result.count, "feeds": serialize(result.feeds)},
            ensure_ascii=False,
            indent=2,
        )
        return {"content": [{"type": "text", "text": text}], "is_error": False}

    async def handle_get_feed_detail(self, ctx, args_map):
        feed_id = args_map.get("feed_id", "")
        xsec_token = args_map.get("xsec_token", "")
        load_all_comments = args_map.get("load_all_comments", False)
        config = None
        if load_all_comments:
            config = CommentLoadConfig(
                click_more_replies=args_map.get("click_more_replies", False),
                max_replies_threshold=args_map.get("max_replies_threshold", 10),
                max_comment_items=args_map.get("max_comment_items", 20),
                scroll_speed=args_map.get("scroll_speed", ""),
            )
        result = await self.xiaohongshu_service.get_feed_detail(
            feed_id, xsec_token, load_all_comments, config
        )
        import json, dataclasses
        text = json.dumps(dataclasses.asdict(result.data), ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "is_error": False}

    async def handle_post_comment(self, ctx, args_map):
        result = await self.xiaohongshu_service.post_comment_to_feed(
            args_map.get("feed_id", ""),
            args_map.get("xsec_token", ""),
            args_map.get("content", ""),
        )
        return {"content": [{"type": "text", "text": result.message}], "is_error": False}

    async def handle_reply_comment(self, ctx, args_map):
        result = await self.xiaohongshu_service.reply_comment_to_feed(
            args_map.get("feed_id", ""),
            args_map.get("xsec_token", ""),
            args_map.get("comment_id", ""),
            args_map.get("user_id", ""),
            args_map.get("content", ""),
        )
        return {"content": [{"type": "text", "text": result.message}], "is_error": False}

    async def handle_like_feed(self, ctx, args_map):
        feed_id = args_map.get("feed_id", "")
        xsec_token = args_map.get("xsec_token", "")
        unlike = args_map.get("unlike", False)
        if unlike:
            result = await self.xiaohongshu_service.unlike_feed(feed_id, xsec_token)
        else:
            result = await self.xiaohongshu_service.like_feed(feed_id, xsec_token)
        return {"content": [{"type": "text", "text": result.message}], "is_error": False}

    async def handle_favorite_feed(self, ctx, args_map):
        feed_id = args_map.get("feed_id", "")
        xsec_token = args_map.get("xsec_token", "")
        unfavorite = args_map.get("unfavorite", False)
        if unfavorite:
            result = await self.xiaohongshu_service.unfavorite_feed(feed_id, xsec_token)
        else:
            result = await self.xiaohongshu_service.favorite_feed(feed_id, xsec_token)
        return {"content": [{"type": "text", "text": result.message}], "is_error": False}


def serialize(obj):
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, list):
        return [serialize(i) for i in obj]

    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}

    if dataclasses.is_dataclass(obj):
        return {k: serialize(v) for k, v in dataclasses.asdict(obj).items()}

    if hasattr(obj, "__dict__"):
        return {k: serialize(v) for k, v in obj.__dict__.items()}

    return str(obj)