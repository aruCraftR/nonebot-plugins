
from nonebot.plugin import on_message, on_notice
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, GroupIncreaseNoticeEvent, NoticeEvent
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP

from .chat import ChatInstance, get_chat_instance, get_chat_instance_directly
from .interface import UserImageMessage, ChatCompletionRequest, UserMessage, SystemMessage
from .utils import UniformedMessage, uniform_chat_text, get_user_name
from .rule import rule_forbidden_id, rule_forbidden_word, rule_available_message
from .flow import ChatCompletionFlow, ImageCCFStep, TextCCFStep

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
    uniformed_chat = await uniform_chat_text(event, bot)
    if not (uniformed_chat.text or uniformed_chat.image_urls):
        return

    if not ((
            chat_instance.config.reply_on_name_mention
            and
            chat_instance.config.bot_name in uniformed_chat.text.lower()
        ) or (
            chat_instance.config.reply_on_at
            and
            (uniformed_chat.wake_up or event.is_tome())
        )):
        if chat_instance.is_group and chat_instance.config.record_other_context:
            if not chat_instance.in_throttle_time():
                await summary_and_record_other_image(chat_instance, uniformed_chat, sender_name)
            if uniformed_chat.text:
                chat_instance.record_other_history(uniformed_chat.text, sender_name)
        if shared.plugin_config.debug:
            shared.logger.info(f'{sender_name} 的消息 {uniformed_chat.text} 不满足生成条件, 已跳过')
        return

    if uniformed_chat.text:
        # 记录用户需要生成对话的文本
        chat_instance.record_chat_history(uniformed_chat.text, sender_name)

    if chat_instance.in_throttle_time():
        return

    if shared.plugin_config.debug:
        shared.logger.info(f'正在准备为 {sender_name} 生成消息')

    flow = ChatCompletionFlow(message, chat_instance)

    if uniformed_chat.image_urls:
        flow.add_step(ImageCCFStep(
            sender_name, uniformed_chat.image_urls
        ))
    if uniformed_chat.text:
        flow.add_step(TextCCFStep())

    await flow.run()


@notice.handle()
async def notice_handler(event: NoticeEvent, bot: Bot):
    return
    if not isinstance(event, GroupIncreaseNoticeEvent): # 群成员增加通知
        return
    chat_instance = get_chat_instance_directly(f'group_{event.group_id}')
    if chat_instance is None or not chat_instance.config.reply_on_welcome:
        return

    user_name = await get_user_name(event, bot, event.user_id)
    if user_name is None:
        return

    if chat_instance.in_throttle_time():
        return

    if shared.plugin_config.debug:
        shared.logger.info(f'正在准备为 {user_name} 生成欢迎消息')

    chat_completion = ChatCompletionRequest(chat_instance)
    await chat_completion.request(
        [
            UserMessage(
                f'欢迎 {user_name} 加入群聊', '',
                provide_local_time=chat_instance.config.provide_local_time
            )
        ], use_history=False
    )

    if chat_completion.success:
        await notice.finish(chat_completion.content)


async def summary_and_record_other_image(chat_instance: ChatInstance, uniformed_chat: UniformedMessage, sender_name: str):
    if not uniformed_chat.image_urls:
        return
    if shared.plugin_config.debug:
        shared.logger.info(f'正在总结图像 {uniformed_chat.image_urls}')

    setp = ImageCCFStep(sender_name, uniformed_chat.image_urls)
    await setp.request_api(chat_instance=chat_instance)
