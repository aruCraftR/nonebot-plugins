
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Bot
from nonebot.permission import Permission

from . import shared


async def admin_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent) and event.group_id == shared.plugin_config.admin_group


async def main_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent) and event.group_id == shared.plugin_config.main_group


permission_admin_group = Permission(admin_group)
permission_main_group = Permission(main_group)
permission_server_group = permission_admin_group | permission_main_group
