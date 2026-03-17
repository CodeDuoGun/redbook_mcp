"""数据模型定义，对应 Go 版本的 xiaohongshu/types.go"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ==================== Feed 相关 ====================

class ImageInfo(BaseModel):
    imageScene: str = ""
    url: str = ""


class Cover(BaseModel):
    width: int = 0
    height: int = 0
    url: str = ""
    fileId: str = ""
    urlPre: str = ""
    urlDefault: str = ""
    infoList: list[ImageInfo] = Field(default_factory=list)


class VideoCapability(BaseModel):
    duration: int = 0


class Video(BaseModel):
    capa: VideoCapability = Field(default_factory=VideoCapability)


class User(BaseModel):
    userId: str = ""
    nickname: str = ""
    nickName: str = ""
    avatar: str = ""


class InteractInfo(BaseModel):
    liked: bool = False
    likedCount: str = "0"
    sharedCount: str = "0"
    commentCount: str = "0"
    collectedCount: str = "0"
    collected: bool = False


class NoteCard(BaseModel):
    type: str = ""
    displayTitle: str = ""
    user: User = Field(default_factory=User)
    interactInfo: InteractInfo = Field(default_factory=InteractInfo)
    cover: Cover = Field(default_factory=Cover)
    video: Optional[Video] = None


class Feed(BaseModel):
    xsecToken: str = ""
    id: str = ""
    modelType: str = ""
    noteCard: NoteCard = Field(default_factory=NoteCard)
    index: int = 0


# ==================== Feed 详情 ====================

class DetailImageInfo(BaseModel):
    width: int = 0
    height: int = 0
    urlDefault: str = ""
    urlPre: str = ""
    livePhoto: bool = False


class Comment(BaseModel):
    id: str = ""
    noteId: str = ""
    content: str = ""
    likeCount: str = "0"
    createTime: int = 0
    ipLocation: str = ""
    liked: bool = False
    userInfo: User = Field(default_factory=User)
    subCommentCount: str = "0"
    subComments: list[Comment] = Field(default_factory=list)
    showTags: list[str] = Field(default_factory=list)


Comment.model_rebuild()


class CommentList(BaseModel):
    list: List[Comment] = Field(default_factory=list)
    cursor: str = ""
    hasMore: bool = False

class VideoMediaInfo(BaseModel):
    video: dict
    stream: dict
    videoId: int

class VideoImageInfo(BaseModel):
    firstFrameFileid: str
    thumbnailFileid: str

class VideoInfo(BaseModel):
    capa: dict
    media: VideoMediaInfo
    image: VideoImageInfo


class FeedDetail(BaseModel):
    noteId: str = ""
    xsecToken: str = ""
    title: str = ""
    desc: str = ""
    type: str = ""
    time: int = 0
    ipLocation: str = ""
    video: VideoInfo = Field(default_factory=VideoInfo) 
    user: User = Field(default_factory=User)
    interactInfo: InteractInfo = Field(default_factory=InteractInfo)
    imageList: list[DetailImageInfo] = Field(default_factory=list)


class FeedDetailResponse(BaseModel):
    note: FeedDetail = Field(default_factory=FeedDetail)
    comments: CommentList = Field(default_factory=CommentList)


# ==================== 用户主页 ====================

class UserBasicInfo(BaseModel):
    gender: int = 0
    ipLocation: str = ""
    desc: str = ""
    imageb: str = ""
    nickname: str = ""
    images: str = ""
    redId: str = ""


class UserInteractions(BaseModel):
    type: str = ""
    name: str = ""
    count: str = "0"


class UserProfileResponse(BaseModel):
    userBasicInfo: UserBasicInfo = Field(default_factory=UserBasicInfo)
    interactions: list[UserInteractions] = Field(default_factory=list)
    feeds: list[Feed] = Field(default_factory=list)


# ==================== 操作结果 ====================

class ActionResult(BaseModel):
    feed_id: str
    success: bool
    message: str


class PostCommentResponse(BaseModel):
    feed_id: str
    success: bool
    message: str


class ReplyCommentResponse(BaseModel):
    feed_id: str
    target_comment_id: str
    target_user_id: str
    success: bool
    message: str


# ==================== 搜索筛选 ====================

class FilterOption(BaseModel):
    sort_by: str = ""
    note_type: str = ""
    publish_time: str = ""
    search_scope: str = ""
    location: str = ""


# ==================== 评论加载配置 ====================

class CommentLoadConfig(BaseModel):
    click_more_replies: bool = False
    max_replies_threshold: int = 10
    max_comment_items: int = 0
    scroll_speed: str = "normal"


def default_comment_load_config() -> CommentLoadConfig:
    return CommentLoadConfig()

