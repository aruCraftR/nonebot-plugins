
from dataclasses import dataclass
from pathlib import Path
import pickle
import re
from traceback import print_exc
from typing import AsyncGenerator, Generator, Iterable, Optional, TYPE_CHECKING
import httpx

from . import shared

if TYPE_CHECKING:
    from .config import McsmInstanceData

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


class McsmAPIError(Exception):
    pass


class McsmAPIParameterError(McsmAPIError):
    pass


class McsmAPIPermissionError(McsmAPIError):
    pass


class McsmAPIInternalError(McsmAPIError):
    pass


class McsmAPIUnknownStatusCodeError(McsmAPIError):
    pass


class AsyncMcsmAPI:
    async_client: httpx.AsyncClient
    base_url: str
    api_key: str

    @classmethod
    def start_async_client(cls):
        cls.async_client = httpx.AsyncClient()
        cls.update_config()

    @classmethod
    async def refresh_async_client(cls):
        cls.update_config()

    @classmethod
    def update_config(cls):
        cls.base_url = shared.plugin_config.mcsm_api_url
        cls.api_key = shared.plugin_config.mcsm_api_key

    @classmethod
    def get_full_url(cls, path: str):
        return f'{cls.base_url}/{path}'

    @classmethod
    def check_status_code(cls, response: httpx.Response):
        match response.status_code:
            case 200:
                return
            case 400:
                raise McsmAPIParameterError(response.url)
            case 403:
                raise McsmAPIPermissionError(f'API key: {cls.api_key}\nURL: {response.url}')
            case 500:
                raise McsmAPIInternalError()
            case _:
                raise McsmAPIUnknownStatusCodeError(response.status_code)

    @classmethod
    async def send_command(cls, instance_data: 'McsmInstanceData', command: str) -> bool:
        response = await cls.async_client.get(cls.get_full_url('protected_instance/command'), params=httpx.QueryParams(
            apikey=cls.api_key,
            uuid=instance_data.instance_id,
            daemonId=instance_data.node_id,
            command=f'{command}\n'
        ))
        cls.check_status_code(response)
        return response.is_success


class AsyncMojangAPI:
    async_client: httpx.AsyncClient
    uuid_cache = {}
    _cache_changed = False
    cahce_file = Path(shared.data_path, 'uuid_cache.pickle')
    player_name_regex = re.compile(r'^[A-Za-z0-9_]+$')

    @classmethod
    def load_cache(cls):
        if not cls.cahce_file.exists():
            return
        with cls.cahce_file.open('rb') as f:
            try:
                cls.uuid_cache = pickle.load(f)
            except Exception:
                print_exc()
            else:
                shared.logger.info(f'成功加载了{len(cls.uuid_cache)}条MojangAPI缓存')

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
        cls.load_cache()

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


api_list = (AsyncMojangAPI, AsyncMcsmAPI)
