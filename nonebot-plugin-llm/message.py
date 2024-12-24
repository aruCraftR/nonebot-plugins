
from nonebot.plugin import on_message, on_notice
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, GroupIncreaseNoticeEvent, NoticeEvent
from nonebot.adapters.onebot.v11.permission import PRIVATE_FRIEND, GROUP

from .chat import ChatInstance, get_chat_instance, get_chat_instance_directly
from .interface import UserImageMessage, ChatCompletionRequest, UserMessage, SystemMessage
from .utils import UniformedMessage, uniform_chat_text, get_user_name
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

    if uniformed_chat.image_urls:
        if uniformed_chat.text:
            # 同时有图像和文本时, 生成图像描述并作为用户输入加入历史记录
            await summary_and_record_chat_image(chat_instance, uniformed_chat, sender_name)
        else:
            # 只有图像时, 直接回复图像描述
            chat_completion = await summary_image(chat_instance, uniformed_chat)
            if chat_completion.success:
                chat_instance.record_chat_history(chat_completion.content, sender_name, token_count=chat_completion.completion_tokens)
            await message.finish(chat_completion.raw_content)   # raw_content不带有给文本模型看的内容标识
    if uniformed_chat.text:
        # 有文本时, 对当前历史记录生成回复
        chat_completion = await ChatCompletionRequest(chat_instance).request()
        if chat_completion.success:
            chat_instance.record_chat_history(chat_completion.content, token_count=chat_completion.completion_tokens)
        await message.finish(chat_completion.content)


@notice.handle()
async def notice_handler(event: NoticeEvent, bot: Bot):
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


async def summary_and_record_chat_image(chat_instance: ChatInstance, uniformed_chat: UniformedMessage, sender_name: str):
    if not uniformed_chat.image_urls:
        return
    chat_completion = await summary_image(chat_instance, uniformed_chat)
    if chat_completion.success:
        chat_instance.record_chat_history(chat_completion.content, sender_name, token_count=chat_completion.completion_tokens)


async def summary_and_record_other_image(chat_instance: ChatInstance, uniformed_chat: UniformedMessage, sender_name: str):
    if not uniformed_chat.image_urls:
        return
    chat_completion = await summary_image(chat_instance, uniformed_chat)
    if chat_completion.success:
        chat_instance.record_other_history(chat_completion.content, sender_name, token_count=chat_completion.completion_tokens)



summary_image_system_msg = SystemMessage('1.总结图像信息时使用中文有条理地回答。2.回答时不进行可能性较低的猜测。3.额外以原始语言输出图像中的所有主要文本内容。', token_count=0)

async def summary_image(chat_instance: ChatInstance, uniformed_chat: UniformedMessage) -> ChatCompletionRequest:
    if shared.plugin_config.debug:
        shared.logger.info(f'正在总结图像 {uniformed_chat.image_urls}')

    chat_completion = ChatCompletionRequest(chat_instance, use_vision_model=True)
    await chat_completion.request(
        [
            summary_image_system_msg,
            UserImageMessage(
                uniformed_chat.image_urls,
                chat_instance.config.vision_model_prompt
            )
        ],
        use_history=False, use_system_message=False, extra_kwargs={'max_tokens': 1024}
    )
    if chat_completion.success:
        chat_completion.content = f'图像, 其中的内容: {chat_completion.content}'
    return chat_completion
