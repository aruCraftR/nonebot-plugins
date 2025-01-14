import contextlib
from time import time

from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.rule import Rule

from . import shared


async def active_member(event: MessageEvent) -> bool:
    if member_info := shared.member_info.get(event.user_id):
        return time() - member_info.last_sent_time <= shared.plugin_config.active_threshold_timestamp
    return False


rule_active_member = Rule(active_member)
