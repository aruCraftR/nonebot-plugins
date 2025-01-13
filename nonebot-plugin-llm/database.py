from typing import Any, Optional, TypedDict, NamedTuple

from . import shared

KNOWLEDGE = 'knowledge'
MEMORY = 'memory'


def init_collection():
    if not shared.db_client.has_collection(KNOWLEDGE):
        shared.db_client.create_collection(KNOWLEDGE, 1024, auto_id=True)
    if not shared.db_client.has_collection(MEMORY):
        shared.db_client.create_collection(MEMORY, 1024, auto_id=True)


class KnowledgeData(TypedDict):
    category: str
    raw_text: str
    vector: list[float]


class MemoryData(TypedDict):
    chat_key: str
    timestamp: int
    sender: str
    raw_text: str
    vector: list[float]


class SearchResult(TypedDict):
    chat_key: str
    timestamp: int
    sender: str
    raw_text: str
    vector: list[float]


class _LLMCollection:
    collection: str
    default_output_fields: Optional[list] = None

    @classmethod
    def insert(cls, data: KnowledgeData) -> dict[str, Any]:
        return shared.db_client.insert(cls.collection, data, timeout=shared.plugin_config.milvus_timeout) # type: ignore

    @classmethod
    def search(cls, vector: list[float], filter: str = "", limit: int = 10, output_fields: Optional[list[str]] = None):
        if output_fields is None:
            output_fields = cls.default_output_fields
        return shared.db_client.search(cls.collection, vector, filter, limit, output_fields, timeout=shared.plugin_config.milvus_timeout)


class Knowledge(_LLMCollection):
    collection = KNOWLEDGE
    default_output_fields = ['category', 'raw_text']


class Memory(_LLMCollection):
    collection = MEMORY
    default_output_fields = ['timestamp', 'sender', 'raw_text']
