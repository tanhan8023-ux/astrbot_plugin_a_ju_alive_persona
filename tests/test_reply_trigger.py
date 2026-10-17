"""显式点名/@ 规则及入口、LLM 防绕过的回归测试。"""
import ast
import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@dataclass
class Plain:
    text: str


@dataclass
class At:
    qq: str | int
    name: str = ""


@dataclass
class Reply:
    chain: list
    sender_id: str = "12345"
    message_str: str = "阿橘"


@dataclass
class Forward:
    chain: list


class Event:
    def __init__(self, messages, self_id="12345", text="", private=False, owner=False):
        self.messages = messages
        self.self_id = self_id
        self.message_str = text
        self.private = private
        self.owner = owner
        self.unified_msg_origin = "same-session"
        self.is_wake = False
        self.is_at_or_wake_command = False
        self.call_llm = False
        self.stopped = False
        self.result = "pending reply"

    def get_messages(self):
        return self.messages

    def get_self_id(self):
        return self.self_id

    def get_message_str(self):
        return self.message_str

    def get_sender_id(self):
        return "3624487365" if self.owner else "67890"

    def is_private_chat(self):
        return self.private

    def should_call_llm(self, disabled):
        # 与 AstrBot 接口一致，True 表示禁止默认 LLM。
        self.call_llm = disabled

    def clear_result(self):
        self.result = None

    def stop_event(self):
        self.stopped = True


def handler(*args, **kwargs):
    def decorate(method):
        method.priority = kwargs.get("priority", 0)
        return method
    return decorate


@pytest.fixture(scope="module")
def plugin_type():
    # 直接加载生产方法，避免测试环境依赖 AstrBot 服务或初始化真实记忆文件。
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AlivePersonaPlugin")
    names = {
        "_is_explicitly_addressed", "_enforce_reply_trigger", "check_reply_trigger",
        "on_llm_request", "on_llm_response", "cmd_forget", "cmd_news",
    }
    original.bases = []
    original.body = [node for node in original.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    namespace = {
        "AstrMessageEvent": Event,
        "Plain": Plain,
        "At": At,
        "filter": SimpleNamespace(event_message_type=handler, EventMessageType=SimpleNamespace(ALL="all")),
        "register_command": handler,
        "register_on_llm_request": handler,
        "register_on_llm_response": handler,
        "logger": Mock(),
    }
    exec(compile(ast.Module(body=[original], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["AlivePersonaPlugin"]


@pytest.fixture
def plugin(plugin_type):
    instance = plugin_type()
    instance.persona = SimpleNamespace(get_name=lambda: "阿橘")
    return instance


@pytest.mark.parametrize("messages,self_id", [
    ([Plain("阿橘，今天怎么样？")], "12345"),
    ([Plain("来聊会儿吧，阿橘")], "12345"),
    ([Plain("阿"), Plain("橘")], "12345"),
    ([At("12345"), Plain("你好")], "12345"),
    ([At(12345)], "12345"),
    ([At("12345")], 12345),
    ([Reply([Plain("旧消息")]), Plain("阿橘，看看这个")], "12345"),
])
def test_name_or_actual_bot_mention_wakes_without_configured_prefix(plugin, messages, self_id):
    event = Event(messages, self_id=self_id)
    asyncio.run(plugin.check_reply_trigger(event))
    assert event.is_wake
    assert event.is_at_or_wake_command
    assert not event.stopped
    assert not event.call_llm


@pytest.mark.parametrize("messages", [
    [],
    [Plain("大家晚上好")],
    [Plain("继续刚才的话题")],
    [Plain("/mood")],
    [Plain("其他唤醒词 你好")],
    [At("67890", name="阿橘"), Plain("你好")],
    [At("all")],
    [At(0)],
    [Reply([Plain("阿橘，之前的问题"), At("12345")]), Plain("嗯")],
    [Forward([Plain("阿橘"), At("12345")])],
    [Plain("@12345 你好")],
])
@pytest.mark.parametrize("private,owner", [(False, False), (True, False), (True, True)])
def test_unaddressed_messages_stop_even_if_framework_already_woke(plugin, messages, private, owner):
    event = Event(messages, text="flattened quote contains 阿橘", private=private, owner=owner)
    event.is_wake = event.is_at_or_wake_command = True
    asyncio.run(plugin.check_reply_trigger(event))
    assert event.stopped
    assert event.call_llm
    assert not event.is_at_or_wake_command
    assert event.result is None


@pytest.mark.parametrize("self_id", [None, "", "0", "all"])
def test_unknown_or_broadcast_bot_id_cannot_match_mentions(plugin, self_id):
    event = Event([At("all"), At(0)], self_id=self_id)
    asyncio.run(plugin.check_reply_trigger(event))
    assert event.stopped


def test_trigger_uses_current_persona_name_and_original_components(plugin):
    plugin.persona.get_name = lambda: "橘子"
    # AstrBot 可在唤醒阶段从 message_str 剥离名字，但原始 Plain 不变。
    event = Event([Plain("橘子，帮忙看看")], text="帮忙看看")
    asyncio.run(plugin.check_reply_trigger(event))
    assert not event.stopped
    event = Event([Plain("阿橘，帮忙看看")])
    asyncio.run(plugin.check_reply_trigger(event))
    assert event.stopped


def test_trigger_does_not_continue_into_next_message_in_same_session(plugin):
    first = Event([Plain("阿橘，在吗")])
    second = Event([Plain("怎么没有人说话")])
    asyncio.run(plugin.check_reply_trigger(first))
    asyncio.run(plugin.check_reply_trigger(second))
    assert not first.stopped
    assert second.stopped


def test_addressing_does_not_override_other_plugin_llm_veto(plugin):
    event = Event([At("12345")])
    event.call_llm = True
    asyncio.run(plugin.check_reply_trigger(event))
    assert event.call_llm
    assert not event.stopped


def test_llm_request_gate_runs_before_memory_or_network_work(plugin):
    plugin.memory = Mock()
    plugin.current_affairs = Mock()
    event = Event([Plain("随便聊聊")], private=True, owner=True)
    request = SimpleNamespace(system_prompt="original", extra_user_content_parts=[])
    asyncio.run(plugin.on_llm_request(event, request))
    assert event.stopped
    assert request.system_prompt == "original"
    assert request.extra_user_content_parts == []
    assert not plugin.memory.mock_calls
    assert not plugin.current_affairs.mock_calls


def test_llm_response_gate_discards_unaddressed_reply_before_random_behavior(plugin):
    plugin.random_behavior = Mock()
    event = Event([Plain("普通群聊")])
    response = SimpleNamespace(completion_text="不该接的话")
    asyncio.run(plugin.on_llm_response(event, response))
    assert event.stopped
    assert response.completion_text == ""
    assert not plugin.random_behavior.mock_calls


@pytest.mark.parametrize("command", ["cmd_forget", "cmd_news"])
@pytest.mark.parametrize("addressed", [False, True])
def test_command_handlers_run_only_after_entry_gate(plugin, command, addressed):
    plugin.memory = Mock()
    plugin.current_affairs = SimpleNamespace(enabled=False)
    parts = [At("12345"), Plain("/command")] if addressed else [Plain("/command")]
    event = Event(parts)
    event.plain_result = lambda text: text
    command_handler = getattr(plugin, command)
    assert plugin.check_reply_trigger.priority > command_handler.priority

    async def dispatch():
        replies = []
        await plugin.check_reply_trigger(event)
        if not event.stopped:
            replies.extend([reply async for reply in command_handler(event)])
        return replies

    replies = asyncio.run(dispatch())
    assert bool(replies) is addressed
    if command == "cmd_forget" and addressed:
        plugin.memory.forget_user.assert_called_once_with(event.get_sender_id())
    else:
        assert not plugin.memory.mock_calls
