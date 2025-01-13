

from traceback import print_exc
from typing import Any, Hashable, NamedTuple, Optional, Iterable, Sequence, Union

from nonebot.exception import MatcherException
from nonebot.matcher import Matcher
from .chat import ChatInstance, HistoryData
from .interface import BaseMessage, ChatCompletionRequest, ModelMessage, SystemMessage, UserImageMessage, UserMessage

Messages = Union[UserMessage, ModelMessage]

class CategorizedSteps(NamedTuple):
    prepare: list['ChatCompletionStep']
    request_api: list['ChatCompletionStep']
    postprocess: list['ChatCompletionStep']


class ChatCompletionFlow:
    def __init__(self, matcher: Matcher | type[Matcher], chat_instance: ChatInstance) -> None:
        self.instance = chat_instance
        self.matcher = matcher
        self._auto_index = 0
        self.steps: list['ChatCompletionStep'] = []
        self.shared_data = {}
        self.merged_history = HistoryData(chat_instance.total_token_limit, copy_from=(chat_instance.history.chat_history, chat_instance.history.other_history))

    def add_data(self, key: Hashable, value: Any):
        self.shared_data[key] = value

    def get_data(self, key: Hashable, default: Optional[Any] = None):
        return self.shared_data.get(key, default)

    async def run(self):
        self.steps.sort(key=lambda x: x._index)
        kwargs = {
            'chat_instance': self.instance,
            'merged_history': self.merged_history,
            'matcher': self.matcher
        }
        categorized_steps = CategorizedSteps(
            [i for i in self.steps if 'prepare' in i.methods],
            [i for i in self.steps if 'request_api' in i.methods],
            [i for i in self.steps if 'postprocess' in i.methods]
        )
        try:
            for step in categorized_steps.prepare:
                await step.prepare(**kwargs)
            for step in categorized_steps.request_api:
                new_messages = await step.request_api(**kwargs)
                if new_messages is None:
                    continue
                self.add_messages(new_messages)
            for step in categorized_steps.postprocess:
                await step.postprocess(**kwargs)
            await self.steps[-1].output_text(**kwargs)
        except MatcherException as e:
            raise e
        except NotImplementedError:
            print_exc()
            await self.matcher.finish('当前的对话补全流程使用了未实现的方法, 具体请查看后台报错')
        except Exception as e:
            print_exc()
            await self.matcher.finish(f'执行对话补全流程时出现意外错误: {str(e)}')

    def add_messages(self, messages: Messages | Sequence[Messages]):
        if isinstance(messages, BaseMessage):
                self.merged_history.add_message(messages) # type: ignore
        elif isinstance(messages, Sequence):
            for i in messages:
                self.merged_history.add_message(i)

    def add_step(self, step: 'ChatCompletionStep', *, index: Optional[int] = None):
        if index is None:
            while self._auto_index in self.steps:
                self._auto_index += 1
            index = self._auto_index
            self._auto_index += 1
        step._index = index
        step.matcher = self.matcher
        step.flow = self
        self.steps.append(step)


class ChatCompletionStep:
    methods: set[str] = set()
    def __init__(self) -> None:
        self._index: int     # 处理流中排序用
        self.flow: ChatCompletionFlow
        self.matcher: Matcher | type[Matcher]

    async def prepare(self, chat_instance: ChatInstance, merged_history: HistoryData):
        pass

    async def request_api(self, chat_instance: ChatInstance, merged_history: HistoryData) -> Optional[Messages | Sequence[Messages]]:
        pass

    async def postprocess(self, chat_instance: ChatInstance, merged_history: HistoryData):
        pass

    async def output_text(self, matcher: Matcher):
        raise NotImplementedError


class TextCCFStep(ChatCompletionStep):
    methods = {'request_api'}
    def __init__(self) -> None:
        super().__init__()
        self.chat_completion: ChatCompletionRequest

    async def request_api(self, chat_instance: ChatInstance, merged_history: HistoryData) -> Optional[Messages]:
        messages = await ChatCompletionRequest.get_messages_list(merged_history.deque, await chat_instance.config.system_message)
        chat_completion = await ChatCompletionRequest(chat_instance).request(messages)
        self.chat_completion = chat_completion
        if chat_completion.success:
            return chat_instance.record_chat_history(chat_completion.content, token_count=chat_completion.completion_tokens)

    async def output_text(self, matcher: Matcher):
        await matcher.finish(self.chat_completion.content)


class ImageCCFStep(ChatCompletionStep):
    methods = {'request_api'}
    summary_image_system_msg = SystemMessage('1.总结图像信息时使用中文有条理地回答。2.回答时不进行可能性较低的猜测。3.额外以原始语言输出图像中的所有主要文本内容。', token_count=0)
    CHAT = 0
    OTHER = 1

    def __init__(self, sender_name: str, image_urls: Iterable[str], *, record_type: int = CHAT) -> None:
        super().__init__()
        self.image_urls = image_urls
        self.sender_name = sender_name
        self.chat_completion: ChatCompletionRequest
        self.record_type = record_type

    async def request_api(self, chat_instance: ChatInstance) -> Optional[Messages]:
        messages = await ChatCompletionRequest.get_messages_list([
            self.summary_image_system_msg,
            UserImageMessage(
                self.image_urls,
                chat_instance.config.vision_model_prompt
            )
        ])
        chat_completion = await ChatCompletionRequest(chat_instance).request(
            messages, ChatCompletionRequest.VISION_MODEL, extra_kwargs={'max_tokens': 1024}
        )
        self.chat_completion = chat_completion
        if chat_completion.success:
            chat_completion.content = f'图像, 其中的内容: {chat_completion.content}'
            match self.record_type:
                case 0:
                    return chat_instance.record_chat_history(chat_completion.content, self.sender_name, token_count=chat_completion.completion_tokens)
                case 1:
                    return chat_instance.record_other_history(chat_completion.content, self.sender_name, token_count=chat_completion.completion_tokens)

    async def output_text(self, matcher: Matcher):
        await matcher.finish(self.chat_completion.raw_content)
