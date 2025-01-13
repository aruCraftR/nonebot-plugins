from typing import TYPE_CHECKING
from .document import Document

from .base import Base

if TYPE_CHECKING:
    from ..ragflow import RAGFlow

class DataSet(Base):
    class ParserConfig(Base):
        def __init__(self, rag: 'RAGFlow', res_dict):
            super().__init__(rag, res_dict)

    def __init__(self, rag: 'RAGFlow', res_dict):
        self.id = ""
        self.name = ""
        self.avatar = ""
        self.tenant_id = None
        self.description = ""
        self.language = "English"
        self.embedding_model = ""
        self.permission = "me"
        self.document_count = 0
        self.chunk_count = 0
        self.chunk_method = "naive"
        self.parser_config = None
        self.pagerank = 0
        for k in list(res_dict.keys()):
            if k not in self.__dict__:
                res_dict.pop(k)
        super().__init__(rag, res_dict)

    async def update(self, update_message: dict):
        res = await self.put(f'/datasets/{self.id}', update_message)
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res["message"])

    async def upload_documents(self, document_list: list[dict]):
        files = [("file", (ele["displayed_name"],ele["blob"])) for ele in document_list]
        res = await self.post(f"/datasets/{self.id}/documents",json=None, files=files)
        res = res.json()
        if res.get("code") == 0:
            return [Document(self.rag, i) for i in res["data"]]
        raise Exception(res.get("message"))

    async def list_documents(self, id: str | None = None, keywords: str | None = None, page: int = 1, page_size: int = 30, orderby: str = "create_time", desc: bool = True):
        res = await self.get(f"/datasets/{self.id}/documents", params={"id": id,"keywords": keywords,"page": page,"page_size": page_size,"orderby": orderby,"desc": desc})
        res = res.json()
        if res.get("code") == 0:
            return [Document(self.rag,document) for document in res["data"].get("docs")]
        raise Exception(res["message"])

    async def delete_documents(self, ids: list[str] | None = None):
        res = await self.rm(f"/datasets/{self.id}/documents", {"ids": ids})
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res["message"])

    async def async_parse_documents(self, document_ids: list[str]):
        res = await self.post(f"/datasets/{self.id}/chunks", {"document_ids": document_ids})
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res.get("message"))

    async def async_cancel_parse_documents(self, document_ids: list[str]):
        res = await self.rm(f"/datasets/{self.id}/chunks", {"document_ids": document_ids})
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res.get("message"))
