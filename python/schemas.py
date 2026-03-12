from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PublishContentArgs:
    title: str
    content: str
    images: List[str]
    tags: Optional[List[str]] = None
    schedule_at: Optional[str] = None
    is_original: Optional[bool] = None
    visibility: Optional[str] = None
    products: Optional[List[str]] = None


@dataclass
class PublishVideoArgs:
    title: str
    content: str
    video: str
    tags: Optional[List[str]] = None
    schedule_at: Optional[str] = None
    visibility: Optional[str] = None
    products: Optional[List[str]] = None


@dataclass
class SearchFeedsArgs:
    keyword: str
    filters: Optional[dict] = None


@dataclass
class FeedDetailArgs:
    feed_id: str
    xsec_token: str
    load_all_comments: Optional[bool] = False
    limit: Optional[int] = 20
    click_more_replies: Optional[bool] = False
    reply_limit: Optional[int] = 10
    scroll_speed: Optional[str] = None


@dataclass
class UserProfileArgs:
    user_id: str
    xsec_token: str


@dataclass
class PostCommentArgs:
    feed_id: str
    xsec_token: str
    content: str


@dataclass
class ReplyCommentArgs:
    feed_id: str
    xsec_token: str
    content: str
    comment_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class LikeFeedArgs:
    feed_id: str
    xsec_token: str
    unlike: Optional[bool] = False


@dataclass
class FavoriteFeedArgs:
    feed_id: str
    xsec_token: str
    unfavorite: Optional[bool] = False