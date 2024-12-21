
from nonebot.plugin import on_message, on_notice
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, GroupIncreaseNoticeEvent
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP

from .chat import get_chat_instance, get_chat_instance_directly
from .interface import request_chat_completion, UserMessage
from .utils import uniform_chat_text, get_user_name
from .rule import rule_forbidden_id, rule_forbidden_word, rule_available_message

from . import shared

message = on_message(
    rule=rule_forbidden_id & rule_forbidden_word & rule_available_message,
    permission=PRIVATE_FRIEND | GROUP,
    priority=shared.plugin_config.event_priority,
    block=shared.plugin_config.block_event
)

notice = on_notice(
    rule=rule_forbidden_id & rule_forbidden_word,
    priority=20,
    block=False
)


@message.handle()
async def message_handler(event: MessageEvent, bot: Bot):
    chat_instance = await get_chat_instance(message, event, bot)
    if not chat_instance.enabled:
        return

    sender_name = await chat_instance.get_user_name(event, bot)
    chat_text, wake_up = await uniform_chat_text(event, bot)
    if not chat_text:
        return

    if not ((
            chat_instance.config.reply_on_name_mention
            and
            chat_instance.config.bot_name in chat_text.lower()
        ) or (
            chat_instance.config.reply_on_at
            and
            (wake_up or event.is_tome())
        )):
        if chat_instance.is_group and chat_instance.config.record_other_context:
            chat_instance.record_other_history(chat_text, sender_name)
        if shared.plugin_config.debug:
            shared.logger.info(f'{sender_name} 的消息 {chat_text} 不满足生成条件, 已跳过')
        return

    chat_instance.record_chat_history(chat_text, sender_name)

    if chat_instance.in_throttle_time():
        return

    if shared.plugin_config.debug:
        shared.logger.info(f'正在准备为 {sender_name} 生成消息')

    response, completion_token_count, success = await request_chat_completion(chat_instance)
    if success:
        chat_instance.record_chat_history(response, token_count=completion_token_count)
    await message.finish(response)


@notice.handle()
async def _(event: GroupIncreaseNoticeEvent, bot: Bot):
    if isinstance(event, GroupIncreaseNoticeEvent): # 群成员增加通知
        chat_key = f'group_{event.group_id}'
    else:
        return
    chat_instance = get_chat_instance_directly(chat_key)
    if chat_instance is None or not chat_instance.config.reply_on_welcome:
        return

    user_name = await get_user_name(event=event, bot=bot, user_id=int(event.get_user_id()))
    if user_name is None:
        return

    if chat_instance.in_throttle_time():
        return

    if shared.plugin_config.debug:
        shared.logger.info(f'正在准备为 {user_name} 生成欢迎消息')

    response, completion_token_count, success = await request_chat_completion(
        chat_instance,
        [
            UserMessage(
                f'欢迎 {user_name} 加入群聊', '',
                provide_local_time=chat_instance.config.provide_local_time
            )
        ]
    )
    if success:
        await message.finish(response)
