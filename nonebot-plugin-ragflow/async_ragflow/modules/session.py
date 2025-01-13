import json
from typing import AsyncGenerator

from .base import Base


class Session(Base):
    def __init__(self, rag, res_dict):
        self.id: str = None # type: ignore
        self.name = "New session"
        self.messages = [{"role": "assistant", "content": "Hi! I am your assistant, can I help you?"}]
        for key,value in res_dict.items():
            if key == "chat_id" and value is not None:
                self.chat_id = None
                self.__session_type = "chat"
            if key == "agent_id" and value is not None:
                self.agent_id = None
                self.__session_type = "agent"
        super().__init__(rag, res_dict)

    async def ask(self, question="",**kwargs) -> AsyncGenerator['Message']:
        if self.__session_type == "agent":
            res = await self._ask_agent(question)
        elif self.__session_type == "chat":
            res = await self._ask_chat(question, **kwargs)
        for line in res.iter_lines():
            if line.startswith("{"):
                json_data = json.loads(line)
                raise Exception(json_data["message"])
            if not line.startswith("data:"):
                continue
            json_data = json.loads(line[5:])
            if json_data["data"] is True or json_data["data"].get("running_status"):
                continue
            answer = json_data["data"]["answer"]
            reference = json_data["data"].get("reference", {})
            temp_dict = {
                "content": answer,
                "role": "assistant"
            }
            if reference and "chunks" in reference:
                chunks = reference["chunks"]
                temp_dict["reference"] = chunks
            yield Message(self.rag, temp_dict)

    async def _ask_chat(self, question: str, **kwargs):
        json_data = {"question": question, "session_id": self.id}
        json_data.update(kwargs)
        return await self.post(f"/chats/{self.chat_id}/completions", json_data)

    async def _ask_agent(self, question: str):
        return await self.post(
            f"/agents/{self.agent_id}/completions",
            {
                "question": question,
                "session_id": self.id
            }
        )

    async def update(self, update_message):
        res = await self.put(f"/chats/{self.chat_id}/sessions/{self.id}", update_message)
        res = res.json()
        if res.get("code") != 0:
            raise Exception(res.get("message"))

class Message(Base):
    def __init__(self, rag, res_dict):
        self.content = "Hi! I am your assistant，can I help you?"
        self.reference = None
        self.role = "assistant"
        self.prompt = None
        self.id = None
        super().__init__(rag, res_dict)
