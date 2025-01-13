#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from typing import Any, Optional

import httpx
from httpx._config import DEFAULT_TIMEOUT_CONFIG

from .modules.chat import Chat
from .modules.chunk import Chunk
from .modules.dataset import DataSet
from .modules.agent import Agent


class RAGFlow:
    def __init__(self, api_key, base_url, version='v1', *, timeout: httpx.Timeout = DEFAULT_TIMEOUT_CONFIG):
        """
        api_url: http://<host_address>/api/v1
        """
        self.user_key = api_key
        self.api_url = f"{base_url}/api/{version}"
        self.authorization_header = {"Authorization": f"Bearer {self.user_key}"}
        self.client = httpx.AsyncClient(headers=self.authorization_header, http2=True, timeout=timeout)

    async def aclose(self):
        await self.client.aclose()

    async def post(self, path: str, json: Optional[dict[str, Any]] = None, files=None) -> httpx.Response:
        return await self.client.post(url=f'{self.api_url}{path}', json=json, files=files)

    async def get(self, path: str, params: Optional[dict[str, Any]] =None) -> httpx.Response:
        return await self.client.get(url=f'{self.api_url}{path}', params=params)

    async def delete(self, path: str, json: dict[str, Any]) -> httpx.Response:
        return await self.client.delete(url=f'{self.api_url}{path}', params=json)

    async def put(self, path: str, json: dict[str, Any]) -> httpx.Response:
        return await self.client.put(url=f'{self.api_url}{path}', json=json)

    async def create_dataset(self, name: str, avatar: str = "", description: str = "", language: str = "English", permission: str = "me",chunk_method: str = "naive", parser_config: Optional[DataSet.ParserConfig] = None) -> DataSet:
        if parser_config:
            parser_config = parser_config.to_json() # type: ignore
        res = await self.post(
            "/datasets",
            {
                "name": name,
                "avatar": avatar,
                "description": description,
                "language": language,
                "permission": permission,
                "chunk_method": chunk_method,
                "parser_config": parser_config
            }
        )
        res = res.json()
        if res.get("code") == 0:
            return DataSet(self, res["data"])
        raise Exception(res["message"])

    async def delete_datasets(self, ids: list[str] | None = None):
        res = await self.delete("/datasets",{"ids": ids})
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res["message"])

    async def get_dataset(self,name: str):
        _list = await self.list_datasets(name=name)
        if len(_list) > 0:
            return _list[0]
        raise Exception(f"Dataset {name} not found")

    async def list_datasets(self, page: int = 1, page_size: int = 30, orderby: str = "create_time", desc: bool = True, id: str | None = None, name: str | None = None) -> list[DataSet]:
        res = await self.get(
            "/datasets",
            {
                "page": page,
                "page_size": page_size,
                "orderby": orderby,
                "desc": desc,
                "id": id,
                "name": name
            }
        )
        res = res.json()
        if res.get("code") == 0:
            return [DataSet(self, data) for data in res['data']]
        raise Exception(res["message"])

    async def create_chat(self, name: str, avatar: str = "", dataset_ids = None, llm: Chat.LLM | None = None, prompt: Chat.Prompt | None = None) -> Chat:
        if dataset_ids is None:
            dataset_ids = []
        dataset_list = list(dataset_ids)

        if llm is None:
            llm = Chat.LLM(
                self,
                {
                    "model_name": None,
                    "temperature": 0.1,
                    "top_p": 0.3,
                    "presence_penalty": 0.4,
                    "frequency_penalty": 0.7,
                    "max_tokens": 512
                }
            )
        if prompt is None:
            prompt = Chat.Prompt(
                self,
                {
                    "similarity_threshold": 0.2,
                    "keywords_similarity_weight": 0.7,
                    "top_n": 8,
                    "variables": [
                        {
                            "key": "knowledge",
                            "optional": True
                        }
                    ],
                    "rerank_model": "",
                    "empty_response": None,
                    "opener": None,
                    "show_quote": True,
                    "prompt": None
                }
            )
            if prompt.opener is None:
                prompt.opener = "Hi! I'm your assistant, what can I do for you?"
            if prompt.prompt is None:
                prompt.prompt = (
                    "You are an intelligent assistant. Please summarize the content of the knowledge base to answer the question. "
                    "Please list the data in the knowledge base and answer in detail. When all knowledge base content is irrelevant to the question, "
                    "your answer must include the sentence 'The answer you are looking for is not found in the knowledge base!' "
                    "Answers need to consider chat history.\nHere is the knowledge base:\n{knowledge}\nThe above is the knowledge base."
                )

        temp_dict = {
            "name": name,
            "avatar": avatar,
            "dataset_ids": dataset_list,
            "llm": llm.to_json(),
            "prompt": prompt.to_json()
        }
        res = await self.post("/chats", temp_dict)
        res = res.json()
        if res.get("code") == 0:
            return Chat(self, res["data"])
        raise Exception(res["message"])

    async def delete_chats(self,ids: list[str] | None = None):
        res = await self.delete('/chats', {"ids":ids})
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res["message"])

    async def list_chats(self, page: int = 1, page_size: int = 30, orderby: str = "create_time", desc: bool = True, id: str | None = None, name: str | None = None) -> list[Chat]:
        res = await self.get("/chats",{"page": page, "page_size": page_size, "orderby": orderby, "desc": desc, "id": id, "name": name})
        res = res.json()
        if res.get("code") == 0:
            return [Chat(self, data) for data in res['data']]
        raise Exception(res["message"])


    async def retrieve(self, dataset_ids: list[str], document_ids: Optional[list[str]] =None, question: str = "", page=1, page_size=30, similarity_threshold=0.2, vector_similarity_weight=0.3, top_k=1024, rerank_id: str | None = None, keyword:bool=False):
            if document_ids is None:
                document_ids = []
            data_json ={
                "page": page,
                "page_size": page_size,
                "similarity_threshold": similarity_threshold,
                "vector_similarity_weight": vector_similarity_weight,
                "top_k": top_k,
                "rerank_id": rerank_id,
                "keyword": keyword,
                "question": question,
                "dataset_ids": dataset_ids,
                "documents": document_ids
            }
            # Send a POST request to the backend service (using requests library as an example, actual implementation may vary)
            res = await self.post('/retrieval',json=data_json)
            res = res.json()
            if res.get("code") == 0:
                return [Chunk(self, i) for i in res["data"].get("chunks")]
            raise Exception(res.get("message"))


    async def list_agents(self, page: int = 1, page_size: int = 30, orderby: str = "update_time", desc: bool = True, id: str | None = None, title: str | None = None) -> list[Agent]:
        res = await self.get("/agents",{"page": page, "page_size": page_size, "orderby": orderby, "desc": desc, "id": id, "title": title})
        res = res.json()
        if res.get("code") == 0:
            return [Agent(self, data) for data in res['data']]
        raise Exception(res["message"])
