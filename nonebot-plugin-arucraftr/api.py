from dataclasses import dataclass
from typing import AsyncGenerator, Generator, Iterable
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
    async def get_online_uuid(cls, player_name: str) -> PlayerInfo:
        response = await cls.async_client.get(f'https://api.mojang.com/users/profiles/minecraft/{player_name}')
        return cls.PlayerInfo(**response.json())

    @classmethod
    async def get_online_uuid_list(cls, player_names: Iterable[str]) -> list[PlayerInfo]:
        response = await cls.async_client.post('https://api.mojang.com/profiles/minecraft', json=player_names)
        return [cls.PlayerInfo(**i) for i in response.json()]


api_list = (AsyncMojangAPI,)
