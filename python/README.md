# xiaohongshu-mcp Python 版

小红书 MCP 服务的 Python 实现，功能与 Go 版本完全一致。  
使用 **Playwright** 替代 go-rod 做浏览器自动化，使用官方 **MCP Python SDK** 暴露 13 个工具。

## 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip
- Chrome / Chromium 浏览器

## 安装

```bash
cd python

# 使用 uv（推荐）
uv sync
uv run playwright install chromium

# 或使用 pip
pip install -e .
playwright install chromium
```

## 环境变量

在 `python/` 目录下创建 `.env` 文件（可选）：

```env
# 是否无头模式运行（默认 true）
HEADLESS=true

# Chrome/Chromium 可执行文件路径（不填则使用 Playwright 自带）
# CHROME_BIN=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome

# 代理（可选）
# XHS_PROXY=http://user:pass@host:port

# cookies 文件路径（默认 cookies.json）
# COOKIES_PATH=/path/to/cookies.json
```

## 运行

```bash
cd python

# 直接运行（stdio MCP 模式）
uv run python main.py

# 或
python main.py
```

## 在 Cursor / Claude Desktop 中配置

在 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "xiaohongshu": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/xiaohongshu-mcp/python"
    }
  }
}
```

## 支持的工具（13 个）

| 工具名 | 说明 |
|---|---|
| `check_login_status` | 检查登录状态 |
| `get_login_qrcode` | 获取登录二维码 |
| `delete_cookies` | 删除 cookies / 重置登录 |
| `publish_content` | 发布图文内容 |
| `publish_with_video` | 发布视频内容（本地文件） |
| `list_feeds` | 获取首页 Feed 列表 |
| `search_feeds` | 搜索内容 |
| `get_feed_detail` | 获取笔记详情 + 评论 |
| `user_profile` | 获取用户主页 |
| `post_comment_to_feed` | 发表评论 |
| `reply_comment_in_feed` | 回复评论 |
| `like_feed` | 点赞 / 取消点赞 |
| `favorite_feed` | 收藏 / 取消收藏 |

## 目录结构

```
python/
  xiaohongshu/
    __init__.py
    types.py          # Pydantic 数据模型
    login.py          # 扫码登录
    feeds.py          # 首页 Feed 列表
    search.py         # 搜索
    feed_detail.py    # 笔记详情 + 评论滚动加载
    publish.py        # 图文发布
    publish_video.py  # 视频发布
    comment_feed.py   # 发表/回复评论
    like_favorite.py  # 点赞/收藏
    user_profile.py   # 用户主页
  browser.py          # Playwright 浏览器工厂
  cookies.py          # Cookie 持久化
  service.py          # 业务编排层
  mcp_server.py       # MCP 工具注册 + 处理器
  main.py             # 程序入口
  pyproject.toml
```

## 首次使用：扫码登录

1. 调用 `get_login_qrcode` 工具，获取二维码图片
2. 用小红书 App 扫码
3. 登录成功后 cookies 自动保存，后续操作无需重复登录
4. 如需重新登录，调用 `delete_cookies` 后再重新扫码

