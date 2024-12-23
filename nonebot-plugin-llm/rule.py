import contextlib

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.rule import Rule

from . import shared


async def forbidden_id(event: MessageEvent) -> bool:
    with contextlib.suppress(ValueError):
        if int(event.get_user_id()) in shared.plugin_config.forbidden_users:
            return False
    return (
        not isinstance(event, GroupMessageEvent)
        or event.group_id not in shared.plugin_config.forbidden_groups
    )


async def forbidden_word(event: MessageEvent) -> bool:
    for w in shared.plugin_config.forbidden_words:
        if str(w).lower() in event.get_message().extract_plain_text().lower():
            if shared.plugin_config.debug:
                shared.logger.info(f'检测到屏蔽词 {w}')
            return False
    return True


async def available_message(event: MessageEvent) -> bool:
    plaintext = event.get_plaintext()
    if shared.plugin_config.debug:
        shared.logger.info(', '.join(f'{i.type}[{str(i.data)}]' for i in event.message))
    if (not event.get_message()) or (shared.plugin_config.only_text_message and not plaintext):
        if shared.plugin_config.debug:
            shared.logger.info('跳过空消息')
        return False
    return not any(
        i and plaintext.lstrip().startswith(i)
        for i in shared.nonebot_config.command_start
    )


rule_forbidden_id = Rule(forbidden_id)
rule_forbidden_word = Rule(forbidden_word)
rule_available_message = Rule(available_message)
