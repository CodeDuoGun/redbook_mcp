from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mcp.server.fastmcp import FastMCP

def setup_routes(app_server):

    app: FastAPI = app_server.app
    mcp_server: FastMCP = app_server.mcp_server

    # -------------------------
    # CORS Middleware
    # -------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------
    # Error Handling Middleware
    # -------------------------
    @app.middleware("http")
    async def error_handling(request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )

    # -------------------------
    # Health Check
    # -------------------------
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # -------------------------
    # MCP Endpoint — mounted as an ASGI sub-app
    # StreamableHTTPSessionManager lifespan is managed in AppServer.start()

    # mcp_server = Server("xiaohongshu")
    mcp_app = mcp_server.streamable_http_app()


    @app.api_route("/mcp", methods=["GET", "POST"])
    @app.api_route("/mcp/{path:path}", methods=["GET", "POST"])
    async def mcp_handler(request: Request, path: str = ""):
        return await mcp_app(request.scope, request.receive, request._send)

    # -------------------------
    # API v1 Router
    # -------------------------
    from fastapi import APIRouter

    api = APIRouter(prefix="/api/v1")
    # api = APIRouter(prefix="")

    # login
    api.get("/login/status")(app_server.check_login_status_handler)
    api.get("/login/qrcode")(app_server.get_login_qrcode_handler)
    api.delete("/login/cookies")(app_server.delete_cookies_handler)

    # publish
    api.post("/publish")(app_server.publish_handler)
    api.post("/publish_video")(app_server.publish_video_handler)

    # feeds
    api.get("/feeds/list")(app_server.list_feeds_handler)
    api.get("/feeds/search")(app_server.search_feeds_handler)
    api.post("/feeds/search")(app_server.search_feeds_handler)
    api.post("/feeds/detail")(app_server.get_feed_detail_handler)

    # comment
    api.post("/feeds/comment")(app_server.post_comment_handler)
    api.post("/feeds/comment/reply")(app_server.reply_comment_handler)

    # user
    api.post("/user/profile")(app_server.user_profile_handler)
    api.get("/user/me")(app_server.my_profile_handler)

    app.include_router(api)