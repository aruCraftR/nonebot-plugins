import contextlib

from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, NoticeEvent
from nonebot.rule import Rule

from . import shared
from .utils import is_active_member


async def active_member(event: MessageEvent) -> bool:
    if member_info := shared.member_info.get(event.user_id):
        return is_active_member(member_info)
    return False


async def available_message(event: MessageEvent) -> bool:
    plaintext = event.get_plaintext()
    if shared.plugin_config.debug:
        shared.logger.info(', '.join(f'{i.type}[{str(i.data)}]' for i in event.message))
    if not event.get_message():
        if shared.plugin_config.debug:
            shared.logger.info('跳过空消息')
        return False
    return not any(
        i and plaintext.lstrip().startswith(i)
        for i in shared.nonebot_config.command_start
    )


async def forbidden_id(event: MessageEvent) -> bool:
    with contextlib.suppress(ValueError):
        if event.user_id in shared.plugin_config.forbidden_users:
            return False
    return True


async def from_main_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent) and event.group_id == shared.plugin_config.main_group


async def from_admin_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent) and event.group_id == shared.plugin_config.admin_group


rule_forbidden_id = Rule(forbidden_id)
rule_available_message = Rule(available_message)
rule_active_member = Rule(active_member)
rule_from_main_group = Rule(from_main_group)
rule_from_admin_group = Rule(from_admin_group)
