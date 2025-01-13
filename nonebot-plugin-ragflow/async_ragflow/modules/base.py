from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from httpx import Response
    from ..ragflow import RAGFlow


class Base(object):
    def __init__(self, rag: 'RAGFlow', res_dict: dict):
        self.rag = rag
        for k, v in res_dict.items():
            self.__dict__[k] = Base(rag, v) if isinstance(v, dict) else v

    def to_json(self) -> dict[str, Any]:
        pr = {}
        for name in dir(self):
            value = getattr(self, name)
            if not name.startswith('__') and not callable(value) and name != "rag":
                pr[name] = value.to_json() if isinstance(value, Base) else value
        return pr

    async def post(self, path, json=None, files=None) -> 'Response':
        return await self.rag.post(path, json, files=files)

    async def get(self, path, params=None) -> 'Response':
        return await self.rag.get(path, params)

    async def rm(self, path, json) -> 'Response':
        return await self.rag.delete(path, json)

    async def put(self,path, json) -> 'Response':
        return await self.rag.put(path, json)

    def __str__(self):
        return str(self.to_json())
