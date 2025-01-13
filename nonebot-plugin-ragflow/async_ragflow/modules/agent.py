from typing import Optional, TYPE_CHECKING
from .base import Base
from .session import Session

if TYPE_CHECKING:
    from ..ragflow import RAGFlow


class Agent(Base):
    def __init__(self, rag: 'RAGFlow', res_dict):
        self.id  = None
        self.avatar = None
        self.canvas_type = None
        self.description = None
        self.dsl = None
        super().__init__(rag, res_dict)

    class Dsl(Base):
        def __init__(self,rag,res_dict):
            self.answer = []
            self.components = {
                "begin": {
                    "downstream": ["Answer:China"],
                    "obj": {
                        "component_name": "Begin",
                        "params": {}
                    },
                    "upstream": []
                }
            }
            self.graph = {
                "edges": [],
                "nodes": [
                    {
                        "data": {
                            "label": "Begin",
                            "name": "begin"
                        },
                        "id": "begin",
                        "position": {
                            "x": 50,
                            "y": 200
                        },
                        "sourcePosition": "left",
                        "targetPosition": "right",
                        "type": "beginNode"
                    }
                ]
            }
            self.history =  []
            self.messages =  []
            self.path =  []
            self.reference = []
            super().__init__(rag,res_dict)

    @staticmethod
    async def create_session(id, rag: 'RAGFlow', **kwargs) -> Session:
        res = await rag.post(f"/agents/{id}/sessions", json=kwargs)
        res = res.json()
        if res.get("code") == 0:
            return Session(rag,res.get("data"))
        raise Exception(res.get("message"))

    @staticmethod
    async def list_sessions(agent_id: str, rag: 'RAGFlow', page: int = 1, page_size: int = 30, orderby: str = "create_time", desc: bool = True, id: Optional[str] = None) -> list[Session]:
        params = {"page": page, "page_size": page_size, "orderby": orderby, "desc": desc, "id": id}
        res = await rag.get(f"/agents/{agent_id}/sessions", params=params)
        res = res.json()
        if res.get("code") == 0:
            return [Session(rag, i) for i in res.get("data")]
        raise Exception(res.get("message"))
