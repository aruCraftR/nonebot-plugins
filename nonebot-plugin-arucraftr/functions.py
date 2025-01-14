
from dataclasses import dataclass
from uuid import UUID
import json as jsonlib
from pathlib import Path
from time import strftime, time
from typing import Generator, NamedTuple, Union, Optional

from nonebot.adapters.onebot.v11 import Event, MessageEvent, PrivateMessageEvent, GroupMessageEvent, GroupIncreaseNoticeEvent, Bot

from .api import AsyncMojangAPI
from . import shared


async def update_admin_id_set(bot: Bot):
    admin_member_list = await bot.get_group_member_list(group_id=shared.plugin_config.admin_group)
    shared.admin_id_set = {i['user_id'] for i in admin_member_list}
    if shared.plugin_config.debug:
        shared.logger.debug(shared.admin_id_set)


@dataclass
class MemberInfo:
    user_id: int
    card: str
    last_sent_time: int
    role: str


async def update_member_data(bot: Bot):
    admin_member_list = await bot.get_group_member_list(group_id=shared.plugin_config.main_group)
    shared.member_info.clear()
    for info in admin_member_list:
        if (nickname := info.get('nickname')) is None:
            return
        shared.member_info[info['user_id']] = MemberInfo(
            user_id = info['user_id'],
            card = info.get('card') or nickname,
            last_sent_time = max(info.get('last_sent_time', 0), info.get('join_time', 0)),
            role = info['role']
        )


def get_active_members() -> Generator[MemberInfo]:
    now = time()
    return (i for i in shared.member_info.values() if now - i.last_sent_time <= shared.plugin_config.active_threshold_timestamp)


async def create_whitelist_file() -> tuple[Path, int, int]:
    failure = 0
    success = 0
    data = []
    for i in get_active_members():
        if (player_info := await AsyncMojangAPI.get_online_uuid(i.card)) is None:
            failure += 1
        else:
            success += 1
            data.append({'uuid': str(UUID(player_info.id)), 'name': player_info.name})
    file_path = Path(shared.data_path, f'temp/whitelist{strftime('%y%m%d%H%M')}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        jsonlib.dump(data, f, indent=4)
    AsyncMojangAPI.save_cache()
    return file_path, success, failure


async def get_whitelist_json(indent: Optional[int] = None) -> tuple[str, int, int]:
    failure = 0
    success = 0
    data = []
    for i in get_active_members():
        if (player_info := await AsyncMojangAPI.get_online_uuid(i.card)) is None:
            failure += 1
        else:
            success += 1
            data.append({'uuid': str(UUID(player_info.id)), 'name': player_info.name})
    AsyncMojangAPI.save_cache()
    return jsonlib.dumps(data, indent=indent), success, failure
