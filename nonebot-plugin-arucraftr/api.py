import contextlib
from dataclasses import dataclass
from pathlib import Path
import pickle
import re
from typing import AsyncGenerator, Generator, Iterable, Optional
import httpx

from . import shared

inited = False

async def refresh_async_client():
    for i in api_list:
        await i.refresh_async_client()


def start_async_client():
    global inited
    if inited:
        return
    for i in api_list:
        i.start_async_client()
    inited = True


class AsyncMojangAPI:
    async_client: httpx.AsyncClient
    uuid_cache = {}
    _cache_changed = False
    cahce_file = Path(shared.data_path, 'uuid_cache.pickle')
    player_name_regex = re.compile(r'^\w+$')

    @classmethod
    def load_cache(cls):
        if not cls.cahce_file.exists():
            return
        with cls.cahce_file.open('rb') as f:
            with contextlib.suppress(Exception):
                cls.cache = pickle.load(f)

    @classmethod
    def save_cache(cls):
        if not cls._cache_changed:
            return
        with cls.cahce_file.open('wb') as f:
            pickle.dump(cls.uuid_cache, f)
        cls._cache_changed = False

    @classmethod
    def start_async_client(cls):
        transport = httpx.AsyncHTTPTransport(retries=3, proxy=shared.plugin_config.proxy)
        cls.async_client = httpx.AsyncClient(transport=transport)

    @classmethod
    async def refresh_async_client(cls):
        if cls.async_client:
            await cls.async_client.aclose()
        cls.start_async_client()

    @dataclass(frozen=True, slots=True)
    class PlayerInfo:
        id: str
        name: str

    @classmethod
    async def get_online_uuid(cls, player_name: str, use_cache=True) -> Optional[PlayerInfo]:
        player_name = player_name.strip()
        if not cls.player_name_regex.match(player_name):
            return None
        if use_cache and ((cache := cls.uuid_cache.get(player_name)) is not None):
            if shared.plugin_config.debug:
                shared.logger.info(f'{player_name}使用缓存')
            return cls.PlayerInfo(**cache)
        try:
            if shared.plugin_config.debug:
                shared.logger.info(f'正在获取{player_name}的玩家数据')
            response = await cls.async_client.get(f'https://api.mojang.com/users/profiles/minecraft/{player_name}')
        except httpx.ConnectTimeout:
            return None
        if response.is_success:
            json = cls.uuid_cache[player_name] = response.json()
            cls._cache_changed = True
            return cls.PlayerInfo(**json)
        return None

    @classmethod
    async def get_online_uuid_list(cls, player_names: Iterable[str]) -> list[PlayerInfo]:
        response = await cls.async_client.post('https://api.mojang.com/profiles/minecraft', json=player_names)
        return [cls.PlayerInfo(**i) for i in response.json()]


api_list = (AsyncMojangAPI,)
