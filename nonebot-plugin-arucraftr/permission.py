
from nonebot.adapters.onebot.v11 import MessageEvent, NoticeEvent, RequestEvent
from nonebot.permission import Permission

from . import shared


async def admin_group(event: MessageEvent | NoticeEvent | RequestEvent) -> bool:
    return hasattr(event, 'group_id') and event.group_id == shared.plugin_config.admin_group # type: ignore


async def main_group(event: MessageEvent | NoticeEvent | RequestEvent) -> bool:
    return hasattr(event, 'group_id') and event.group_id == shared.plugin_config.main_group # type: ignore


permission_admin_group = Permission(admin_group)
permission_main_group = Permission(main_group)
permission_server_group = permission_admin_group | permission_main_group
