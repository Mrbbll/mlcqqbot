"""定义表情包浏览、收藏、检索、发送选择和安全删除工具。"""

import re
from pathlib import Path

from pydantic import Field

from features.agent.emojipic import (
    delete_emoji_image,
    get_emoji_image,
    list_emoji_images,
    save_emoji_image,
    search_emoji_images,
)
from features.agent.emojipic.library import EmojiImageIdAmbiguousError
from features.agent.emoji_catalog import emoji_summary
from features.agent.reply_memory import last_sent_emoji
from features.agent.tools.common import NonBlank, ToolArgs, ToolContext, ToolResult, ToolSpec


MAX_SAVES_PER_REPLY = 3
_DELETE_VERB_PATTERN = re.compile(r"(?:删除|删掉|删去|删了|删|移除|清除|清掉|取消收藏)")
_NEGATED_DELETE_PATTERN = re.compile(
    r"(?:不要|别|不必|不需要|不想|禁止|不准|不允许|先别|暂不)\s*"
    r"(?:再\s*)?(?:把.{0,8})?(?:删除|删掉|删去|删了|删|移除|清除|清掉|取消收藏)"
)
_DELETE_DISCUSSION_PATTERN = re.compile(
    r"(?:能否|能不能|可不可以|是否|怎么|如何|要不要|为什么|为何)"
    r"[^，。！？!?；;\n]{0,20}(?:删除|删掉|删去|删了|删|移除|清除|清掉|取消收藏)|"
    r"(?:删除|删掉|删去|删了|删|移除|清除|清掉|取消收藏)"
    r"[^，。！？!?；;\n]{0,12}(?:吗|可以吗|能吗)\s*$"
)
_DELETE_HELP_REQUEST_PATTERN = re.compile(
    r"(?:帮我|帮忙|麻烦|请).{0,8}(?:删除|删掉|删去|删了|删|移除|清除|清掉|取消收藏)"
)


class SaveEmojiArgs(ToolArgs):
    """定义可见图片的序号与收藏分类，不接收模型提供的图片地址。"""

    image_index: int = Field(ge=1, description="本次视觉上下文中的图片序号，从 1 开始。")
    category: NonBlank = Field(description="简短中文分类名，例如开心、无语、疑惑。")
    name: NonBlank = Field(description="根据图片内容取简短名字。")
    tags: list[str] = Field(default_factory=list, max_length=12, description="用于检索的文字标签，最多 12 个。")


class ListEmojiArgs(ToolArgs):
    """定义分页、分类和图片格式筛选。"""

    page: int = Field(default=1, ge=1, description="从 1 开始的页码。")
    page_size: int = Field(default=10, ge=1, le=20, description="每页图片数量。")
    gif_only: bool = Field(default=False, description="是否仅浏览 GIF。")
    category: str = Field(default="", description="完整分类名；空字符串表示所有分类。")


class EmojiQueryArgs(ToolArgs):
    """保留换图条件继承所需的显式字段信息。"""

    query: str = Field(default="", description="情绪或语境关键词；只要求格式或继承上次条件时可为空。")
    gif_only: bool = Field(default=False, description="用户要 GIF 时设为 true；换图时省略可继承上次条件。")
    replace_previous: bool = Field(default=False, description="用户要求换一个时设为 true，排除上一张成功发送的图片。")


class SearchEmojiArgs(EmojiQueryArgs):
    """定义关键词检索数量，不允许模型提供图片路径。"""

    query: str = Field(description="检索关键词；只要求 GIF 或继承换图条件时可为空字符串。")
    limit: int = Field(default=5, ge=1, le=10, description="最多返回几条候选记录。")


class SendEmojiArgs(EmojiQueryArgs):
    """定义按真实图片 ID 或检索词选择一张待发送表情。"""

    image_id: str = Field(default="", description="浏览或搜索返回的完整图片 ID；提供后不重新检索，不得编造。")


def save_emoji(args: SaveEmojiArgs, context: ToolContext) -> ToolResult:
    """收藏宿主当前提供的图片，保持去重与单轮收藏数量限制。"""
    if args.image_index > len(context.image_inputs):
        return ToolResult(False, "invalid_image_index", "收藏失败：图片序号不在本次视觉上下文范围内。")
    if len(context.saved_emoji_images) >= MAX_SAVES_PER_REPLY:
        return ToolResult(False, "save_limit", "本次回复最多自动收藏 3 张图片。")
    image = context.image_inputs[args.image_index - 1]
    try:
        record = save_emoji_image(str(image.get("data_url") or ""), args.category, args.name, args.tags, {
            "group_id": image.get("source_group_id") or context.group_id,
            "message_id": image.get("source_message_id"), "user_id": image.get("source_user_id"),
        })
    except (OSError, RuntimeError, ValueError):
        return ToolResult(False, "emoji_store_unavailable", "收藏失败：本地图片库无法保存该图片。", retryable=True)
    context.saved_emoji_images.append(record["id"])
    context.available_emoji_ids.add(record["id"])
    return ToolResult(True, message="表情包已收藏。", data={
        "id": record["id"], "category": record["category"], "name": record["name"],
        "duplicate": bool(record.get("duplicate")),
    })


def list_emojis(args: ListEmojiArgs, context: ToolContext) -> ToolResult:
    """返回公开图片摘要与完整分页信息，空页不作为执行失败。"""
    try:
        result = list_emoji_images(args.page, args.page_size, gif_only=args.gif_only, category=args.category.strip())
    except (OSError, RuntimeError, ValueError):
        return ToolResult(False, "emoji_store_unavailable", "浏览失败：收藏索引暂时不可用。", retryable=True)
    items = [emoji_summary(item) for item in result["items"]]
    context.available_emoji_ids.update(item["id"] for item in items)
    return ToolResult(True, message="收藏目录浏览完成。", data={
        **result, "items": items,
    })


def query_conditions(args: EmojiQueryArgs, context: ToolContext) -> tuple[str, bool, str] | ToolResult:
    """继承成功发送后的筛选条件，严格区分布尔值未提供和显式 false。"""
    previous = last_sent_emoji(context.group_id) if args.replace_previous else None
    if args.replace_previous and previous is None:
        return ToolResult(False, "no_previous_emoji", "没有近期成功发送的表情包记录，请说明想要的内容或格式。")
    query = args.query
    gif_only = args.gif_only
    if previous:
        if not query.strip():
            query = previous.get("query", "")
        if "gif_only" not in args.model_fields_set:
            gif_only = previous.get("gif_only", False)
    exclude_id = str(previous.get("id") or "") if previous else ""
    if not query.strip() and not gif_only and not exclude_id and not getattr(args, "image_id", "").strip():
        return ToolResult(False, "missing_query", "请提供要表达的语境或关键词。")
    return query, gif_only, exclude_id


def search_emojis(args: SearchEmojiArgs, context: ToolContext) -> ToolResult:
    """检索公开候选图片，查无结果时返回空列表而不伪造匹配。"""
    conditions = query_conditions(args, context)
    if isinstance(conditions, ToolResult):
        return conditions
    query, gif_only, exclude_id = conditions
    try:
        results = search_emoji_images(query, args.limit, gif_only=gif_only, exclude_id=exclude_id)
    except (OSError, RuntimeError, ValueError):
        return ToolResult(False, "emoji_store_unavailable", "检索失败：收藏索引暂时不可用。", retryable=True)
    items = [emoji_summary(item) for item in results]
    context.available_emoji_ids.update(item["id"] for item in items)
    return ToolResult(True, message="表情包检索完成。", data={"items": items})


def select_emoji(args: SendEmojiArgs, context: ToolContext) -> ToolResult:
    """只选择一张待发送图片，实际成功发送的记忆仍由 QQ 发送入口更新。"""
    if not context.group_id.strip():
        return ToolResult(False, "group_required", "表情包发送失败：该工具只支持群聊。")
    if context.pending_emoji_images:
        return ToolResult(False, "already_selected", "本次回复已经选择了一张表情包，不再重复选择。")
    conditions = query_conditions(args, context)
    if isinstance(conditions, ToolResult):
        return conditions
    query, gif_only, exclude_id = conditions
    image_id = args.image_id.strip()
    try:
        if image_id:
            item = get_emoji_image(image_id)
            if item is None:
                return ToolResult(False, "emoji_not_found", "指定 ID 不存在或图片文件不可用，请重新浏览收藏库。")
            if image_id == exclude_id:
                return ToolResult(False, "same_emoji", "指定 ID 就是上一张表情包，请选择其他 ID。")
            if gif_only and Path(item["file"]).suffix.casefold() != ".gif":
                return ToolResult(False, "format_mismatch", "指定图片不是 GIF，请选择 GIF 格式。")
            results = [item]
        else:
            results = search_emoji_images(query, 1, gif_only=gif_only, exclude_id=exclude_id)
    except (OSError, RuntimeError, ValueError):
        return ToolResult(False, "emoji_store_unavailable", "表情包发送失败：收藏索引暂时不可用。", retryable=True)
    if not results:
        message = "没有其他符合条件的表情包，未重复发送上一张。" if args.replace_previous else "收藏库中没有找到适合该语境的表情包。"
        return ToolResult(False, "emoji_not_found", message)
    context.available_emoji_ids.add(str(results[0].get("id") or ""))
    context.pending_emoji_images.append({**results[0], "query": query, "gif_only": gif_only})
    return ToolResult(True, message="已选择表情包，将在文字回复后发送；目前尚未确认发送成功。", data={
        "image": emoji_summary(results[0]), "delivery": "pending",
    })


class DeleteEmojiArgs(ToolArgs):
    """仅接受图库生成的完整十六位图片 ID，不接受名称或路径。"""

    image_id: str = Field(
        pattern=r"^[0-9a-f]{16}$",
        description="用户当前明确给出的完整图片 ID，或本轮浏览/搜索结果返回的完整 ID；不得填写名称或文件路径。",
    )


def user_requested_emoji_deletion(question: str) -> bool:
    """仅把当前消息中的明确删除动作视为删除授权，排除否定和能力询问。"""
    clauses = re.split(r"[，,。！？!?；;\n]", question or "")
    for clause in clauses:
        if not _DELETE_VERB_PATTERN.search(clause):
            continue
        if _NEGATED_DELETE_PATTERN.search(clause):
            continue
        if _DELETE_DISCUSSION_PATTERN.search(clause) and not _DELETE_HELP_REQUEST_PATTERN.search(clause):
            continue
        return True
    return False


def _image_id_was_requested(image_id: str, question: str) -> bool:
    """确认用户当前消息直接提供了完整 ID，而不是从旧对话继承。"""
    return bool(re.search(rf"(?<![0-9a-fA-F]){re.escape(image_id)}(?![0-9a-fA-F])", question or "", re.IGNORECASE))


def delete_emoji(args: DeleteEmojiArgs, context: ToolContext) -> ToolResult:
    """删除本轮已确认或用户当前点名的唯一收藏，不做模糊名称匹配。"""
    if context.emoji_delete_attempted:
        return ToolResult(False, "delete_limit", "本轮最多删除一张收藏表情包。")
    if not user_requested_emoji_deletion(context.question):
        return ToolResult(False, "delete_not_requested", "当前消息没有明确要求删除收藏表情包。")
    if (
        args.image_id not in context.available_emoji_ids
        and not _image_id_was_requested(args.image_id, context.question)
    ):
        return ToolResult(False, "emoji_id_not_confirmed", "该 ID 未在当前消息点名，也不是本轮浏览或搜索得到的结果。")
    if any(item.get("id") == args.image_id for item in context.pending_emoji_images):
        return ToolResult(False, "emoji_pending_delivery", "该表情已排入本轮发送队列，不能同时删除。")

    context.emoji_delete_attempted = True
    try:
        deleted = delete_emoji_image(args.image_id)
    except EmojiImageIdAmbiguousError:
        return ToolResult(False, "ambiguous_emoji_id", "图库中存在重复 ID，无法安全确定目标，未删除任何图片。")
    except ValueError:
        return ToolResult(False, "invalid_emoji_id", "图片 ID 无效，未删除任何图片。")
    except (OSError, RuntimeError):
        return ToolResult(
            False,
            "emoji_store_unavailable",
            "图库更新异常，删除结果未确认；不要重复调用删除工具，先浏览图库确认当前状态。",
        )
    if deleted is None:
        return ToolResult(False, "emoji_not_found", "图库中没有这条可用收藏，未删除其他图片。")

    context.available_emoji_ids.discard(args.image_id)
    return ToolResult(True, message="收藏及索引记录已删除。", data={
        "image": emoji_summary(deleted), "catalog_updated": True,
    })


TOOLS = (
    ToolSpec("save_emoji_image", "收藏当前视觉上下文中的反应表情图；普通照片、文档和截图不要自动收藏。", SaveEmojiArgs, save_emoji),
    ToolSpec("list_emoji_images", "分页浏览收藏目录，无需关键词；按 has_more 翻页，使用真实图片 ID 选择图片。", ListEmojiArgs, list_emojis),
    ToolSpec("search_emoji_images", "根据情绪或语境检索收藏表情；用户要 GIF 时设置 gif_only=true。", SearchEmojiArgs, search_emojis),
    ToolSpec("send_emoji_image", "选择一张收藏表情包待发送，优先用真实 image_id；换图设 replace_previous=true，省略 gif_only 可继承上次条件。", SendEmojiArgs, select_emoji),
    ToolSpec(
        "delete_emoji_image",
        "超级用户明确要求删除收藏时，按完整 ID 删除一张图片；必须来自本轮浏览/搜索结果或当前消息明确提供的 ID。若描述对应多个候选，先询问，不得猜测。",
        DeleteEmojiArgs,
        delete_emoji,
        True,
        "删除收藏表情包仅限超级用户使用。",
    ),
)
