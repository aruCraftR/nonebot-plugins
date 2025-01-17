
from typing import NamedTuple, Union, Optional

from nonebot.adapters.onebot.v11 import Event, MessageEvent, PrivateMessageEvent, GroupMessageEvent, GroupIncreaseNoticeEvent, Bot

from .name import EMOJI_NAME
from . import shared


def is_anonymous(event: Event):
    # isinstance(event, GroupMessageEvent) and event.sub_type == 'anonymous' and event.anonymous
    return getattr(event, 'anonymous', None) is not None and getattr(event, 'sub_type', None) == 'anonymous'


async def get_user_name(event: Union[MessageEvent, GroupIncreaseNoticeEvent], bot: Bot, user_id: int) -> Optional[str]:
    if is_anonymous(event):
        return f'[匿名]{event.anonymous.name}' # type: ignore

    if isinstance(event, (GroupMessageEvent, GroupIncreaseNoticeEvent)):
        user_info = await bot.get_group_member_info(group_id=event.group_id, user_id=user_id)
        user_name = user_info.get('nickname', None)
        if shared.plugin_config.use_group_card:
            user_name = user_info.get('card', None) or user_name
    else:
        user_name = event.sender.nickname if event.sender else event.get_user_id()

    return user_name


class UniformedMessage(NamedTuple):
    wake_up: bool
    text: Optional[str]
    image_urls: list[str]


async def uniform_chat_text(event: MessageEvent, bot: Bot, use_raw=False) -> UniformedMessage:
    """将部分类型的消息段转化为利于理解的纯文本并拼接"""
    # if not isinstance(event, GroupMessageEvent):
    #     return event.raw_message if use_raw else event.get_plaintext(), False

    if use_raw:
        return UniformedMessage('@全体成员' in event.raw_message, event.raw_message, [])

    wake_up = False
    msgs = []
    img_urls = []
    for seg in event.message:
        match seg.type:
            case 'text':    # 纯文本
                msgs.append(seg.data.get('text', ''))
            case 'at':      # @
                target = seg.data.get('qq')
                if not target:
                    continue
                if target == 'all':
                    msgs.append('@全体成员')
                    wake_up = True
                else:
                    user_name = await get_user_name(event=event, bot=bot, user_id=int(target))
                    if user_name:
                        msgs.append(f'@{user_name}')
            case 'face':     # Emoji
                if name := EMOJI_NAME.get(seg.data.get('id')): # type: ignore
                    msgs.append(name)
            case 'image':    # 图像表情
                if summary := seg.data.get('summary'):
                    if summary != '[动画表情]':
                        msgs.append(summary)
                elif url := seg.data.get('url'):
                    img_urls.append(url)
            case 'poke':     # 戳一戳
                if name := seg.data.get('name'):
                    msgs.append(name)
    return UniformedMessage(wake_up, ''.join(msgs), img_urls)


async def get_chat_type(event: MessageEvent) -> tuple[str, Optional[bool]]:
    """生成聊天标识名称"""
    if isinstance(event, GroupMessageEvent):
        return f'group_{event.group_id}', True
    elif isinstance(event, PrivateMessageEvent):
        return f'private_{event.get_user_id()}', False
    else:
        if shared.plugin_config.debug:
            shared.logger.info(f'未知消息来源: {event.get_session_id()}')
        return f'unknown_{event.get_session_id()}', None

