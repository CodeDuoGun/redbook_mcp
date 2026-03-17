from schemas import (
    PublishContentArgs, 
    PublishVideoArgs, 
    SearchFeedsArgs, 
    FeedDetailArgs, 
    UserProfileArgs, 
    PostCommentArgs, 
    ReplyCommentArgs, 
    LikeFeedArgs,
    FavoriteFeedArgs,
    CreativeInspirationArgs,
    )

import logging
from mcp.server.fastmcp import FastMCP
from mcp.server import Server

logger = logging.getLogger(__name__)


def init_mcp_server(app_server):

    server = FastMCP(
        name="xiaohongshu-mcp",
        # json_response=True
        # version="2.0.0"
    )

    register_tools(server, app_server)

    logger.info("MCP Server initialized")

    return server


import traceback
from functools import wraps


def with_panic_recovery(tool_name):
    def decorator(func):

        @wraps(func)
        async def wrapper(ctx, args):

            try:
                return await func(ctx, args)

            except Exception as e:
                logger.error(f"Tool {tool_name} panic: {e}")
                logger.error(traceback.format_exc())

                return {
                    "is_error": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"工具 {tool_name} 执行时发生内部错误: {e}"
                        }
                    ]
                }

        return wrapper

    return decorator


def register_tools(server, app_server):

    @server.tool(
        name="check_login_status",
        description="检查小红书登录状态"
    )
    @with_panic_recovery("check_login_status")
    async def check_login_status(ctx, args):
        return await app_server.handle_check_login_status(ctx)


    @server.tool(
        name="get_login_qrcode",
        description="获取登录二维码"
    )
    @with_panic_recovery("get_login_qrcode")
    async def get_login_qrcode(ctx, args):
        return await app_server.handle_get_login_qrcode(ctx)


    @server.tool(
        name="delete_cookies",
        description="删除 cookies 文件"
    )
    @with_panic_recovery("delete_cookies")
    async def delete_cookies(ctx, args):
        return await app_server.handle_delete_cookies(ctx)

    @server.tool(
        name="publish_content",
        description="发布小红书图文内容"
    )
    @with_panic_recovery("publish_content")
    async def publish_content(ctx, args: PublishContentArgs):

        args_map = {
            "title": args.title,
            "content": args.content,
            "images": args.images,
            "tags": args.tags,
            "schedule_at": args.schedule_at,
            "is_original": args.is_original,
            "visibility": args.visibility,
            "products": args.products
        }

        return await app_server.handle_publish_content(ctx, args_map)

    @server.tool(
        name="search_feeds",
        description="搜索小红书内容"
    )
    @with_panic_recovery("search_feeds")
    async def search_feeds(ctx, args: SearchFeedsArgs):

        return await app_server.handle_search_feeds(ctx, args)


    @server.tool(
        name="get_feed_detail",
        description="获取小红书笔记详情"
    )
    @with_panic_recovery("get_feed_detail")
    async def get_feed_detail(ctx, args: FeedDetailArgs):

        args_map = {
            "feed_id": args.feed_id,
            "xsec_token": args.xsec_token,
            "load_all_comments": args.load_all_comments
        }

        if args.load_all_comments:
            args_map["max_comment_items"] = args.limit or 20
            args_map["max_replies_threshold"] = args.reply_limit or 10
            args_map["click_more_replies"] = args.click_more_replies
            args_map["scroll_speed"] = args.scroll_speed

        return await app_server.handle_get_feed_detail(ctx, args_map)
    

    @server.tool(
        name="post_comment_to_feed",
        description="发表评论"
    )
    @with_panic_recovery("post_comment_to_feed")
    async def post_comment(ctx, args: PostCommentArgs):

        args_map = {
            "feed_id": args.feed_id,
            "xsec_token": args.xsec_token,
            "content": args.content
        }

        return await app_server.handle_post_comment(ctx, args_map)

    @server.tool(
        name="reply_comment_in_feed",
        description="回复评论"
    )
    async def reply_comment(ctx, args: ReplyCommentArgs):

        if not args.comment_id and not args.user_id:
            return {
                "is_error": True,
                "content": [
                    {"type": "text", "text": "缺少 comment_id 或 user_id"}
                ]
            }

        args_map = {
            "feed_id": args.feed_id,
            "xsec_token": args.xsec_token,
            "comment_id": args.comment_id,
            "user_id": args.user_id,
            "content": args.content
        }

        return await app_server.handle_reply_comment(ctx, args_map)


    @server.tool(
        name="like_feed",
        description="点赞或取消点赞"
    )
    async def like_feed(ctx, args: LikeFeedArgs):

        args_map = {
            "feed_id": args.feed_id,
            "xsec_token": args.xsec_token,
            "unlike": args.unlike
        }

        return await app_server.handle_like_feed(ctx, args_map)


    @server.tool(
        name="favorite_feed",
        description="收藏或取消收藏"
    )
    async def favorite_feed(ctx, args: FavoriteFeedArgs):

        args_map = {
            "feed_id": args.feed_id,
            "xsec_token": args.xsec_token,
            "unfavorite": args.unfavorite
        }

        return await app_server.handle_favorite_feed(ctx, args_map)


    @server.tool(
        name="creative_inspiration",
        description=(
            "Agent工具：根据用户提供的标题、正文、图片或视频，自动完成以下全流程：\n"
            "1. 解析图片/视频的风格、内容、构图特点；\n"
            "2. 生成最多3套新的标题+文案方案；\n"
            "3. 用AI自动生成对应的新图片（图文模式）或新视频（视频模式）；\n"
            "4. 将每套方案以「仅自己可见」自动发布到小红书。\n"
            "传入图片时触发图文模式，传入视频时触发视频模式。"
        )
    )
    @with_panic_recovery("creative_inspiration")
    async def creative_inspiration(ctx, args: CreativeInspirationArgs):

        args_map = {
            "title": args.title,
            "content": args.content,
            "images": args.images,
            "video": args.video,
            "topic": args.topic,
        }

        return await app_server.handle_creative_inspiration(ctx, args_map)


def convert_to_mcp_result(result):

    contents = []

    for c in result["content"]:

        if c["type"] == "text":
            contents.append({
                "type": "text",
                "text": c["text"]
            })

        elif c["type"] == "image":
            contents.append({
                "type": "image",
                "data": c["data"],
                "mimeType": c["mime_type"]
            })

    return {
        "content": contents,
        "is_error": result.get("is_error", False)
    }