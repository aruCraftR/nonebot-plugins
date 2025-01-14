import contextlib

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Bot
from nonebot.permission import Permission

from . import shared


async def admin_group(event: MessageEvent) -> bool:
    return event.user_id in shared.admin_id_set


permission_admin_group = Permission(admin_group)
