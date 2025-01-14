import contextlib
from time import time

from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.rule import Rule

from . import shared
from .utils import is_active_member


async def active_member(event: MessageEvent) -> bool:
    if member_info := shared.member_info.get(event.user_id):
        return await is_active_member(member_info)
    return False


rule_active_member = Rule(active_member)
