"""温和底色、可选吐槽及每轮策略的回归测试。"""
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from a_ju_alive_persona.emotion import EmotionSystem
from a_ju_alive_persona.persona import DEFAULT_PERSONA, PersonaEngine
from a_ju_alive_persona.persona_style import PersonaStyleState


@pytest.fixture
def style():
    state = PersonaStyleState(trait_anchor_rate=0.0)
    state._random = lambda chance: False
    return state


def decide(style, message, relation="stranger", special=False, mood="正常"):
    return style.decide("session", message, relation, {"mood": mood}, special)


@pytest.mark.parametrize("relation", ["stranger", "acquaintance", "friend", "close_friend"])
def test_default_and_normal_disagreement_stay_gentle(style, relation):
    for message in ["聊一会儿吧", "这个结论的证据是什么？", "你这说法是不是有点双标？"]:
        result = decide(style, message, relation, mood="热闹")
        assert result["tone"] == "gentle"
        assert "拿不准就温和" in result["tone_guidance"]
    assert "按情境可选" in decide(style, "这个结论的证据是什么？", relation)["mode"]


@pytest.mark.parametrize("message", [
    "今天很难过，为什么大家老怼我，是不是我很差？",
    "哈哈我最近有点焦虑，你吐槽我一下吧",
    "对不起，我说错了，你怼我吧",
    "哈哈别再怼我了，真的不好笑",
    "认真一点说，我不是开玩笑",
    "我被骂了，为什么他说我是个废物？",
    "我是不是没用，怼我两句吧",
    "我今天有点累，为什么总这样",
    "我有点烦，你又双标了",
    "你为什么总是怼我？",
    "别再阴阳怪气了",
])
def test_distress_apology_and_opt_out_override_teasing(style, message):
    result = decide(style, message, "close_friend", mood="热闹")
    assert result["intent"] == "emotional"
    assert result["tone"] == "gentle"
    assert "本轮不毒舌、不补刀" in result["tone_guidance"]


@pytest.mark.parametrize("message", [
    "这个报错怎么修？",
    "帮我看看这段逻辑有什么问题",
    "如何配置压力测试？",
    "累加和怎么计算？",
    "麻烦教我设置 API",
])
def test_help_is_gentle_without_confusing_technical_terms_with_distress(style, message):
    result = decide(style, message, "friend")
    assert result["intent"] in ("technical", "logic")
    assert result["tone"] == "gentle"
    assert "本轮不毒舌" in result["tone_guidance"]


@pytest.mark.parametrize("message", ["怼我两句吧", "来点毒舌", "帮我吐槽我一下"])
def test_explicit_lighthearted_invitation_keeps_optional_teasing(style, message):
    result = decide(style, message)
    assert result["tone"] == "playful"
    assert "可选" in result["tone_guidance"]
    assert "不攻击人格" in result["tone_guidance"]


def test_mentioning_being_teased_is_not_an_invitation(style):
    for message in ["他又怼我了", "他怼我两句就走了", "你怼我干什么"]:
        assert decide(style, message, "friend")["tone"] == "gentle"


def test_familiar_playful_chat_is_not_permission_to_tease_strangers(style):
    message = "哈哈又摸鱼了，逗你玩的"
    assert decide(style, message, "friend")["tone"] == "playful"
    assert decide(style, message, "close_friend")["tone"] == "playful"
    assert decide(style, message, "stranger", mood="热闹")["tone"] == "gentle"


@pytest.mark.parametrize("message", ["少废话，闭嘴", "你又双标了，还在偷换概念"])
def test_provocation_allows_firm_but_bounded_reply(style, message):
    result = decide(style, message)
    assert result["tone"] == "firm"
    assert "最多一句" in result["tone_guidance"]
    assert "不辱骂、不升级争吵" in result["tone_guidance"]


def test_owner_keeps_warmth_even_with_teasing_invitation_or_provocation(style):
    for message in ["来点毒舌", "少废话，闭嘴", "你这结论没有证据"]:
        result = decide(style, message, "close_friend", special=True)
        assert result["tone"] == "gentle"
        assert "对小栎主人保持温柔暖心" in result["tone_guidance"]


def test_tone_returns_to_gentle_when_playful_chat_turns_serious(style):
    assert decide(style, "哈哈，逗你玩的", "friend")["tone"] == "playful"
    assert decide(style, "别闹，认真一点说", "friend")["tone"] == "gentle"
    assert decide(style, "这个说法的证据呢？", "friend")["tone"] == "gentle"


def test_active_and_fallback_personas_have_the_same_contextual_tone_rules(tmp_path):
    plugin_dir = Path(__file__).resolve().parents[1]
    active = json.loads((plugin_dir / "data" / "persona_a_ju.json").read_text(encoding="utf-8"))
    assert active == DEFAULT_PERSONA
    engine = PersonaEngine(str(tmp_path))
    prompt = engine.build_system_prompt("")
    assert active["sharp_tongue"]["enabled"] is True
    assert "默认温和友善" in prompt
    assert "毒舌是可选调味" in prompt
    assert "逻辑有漏洞不等于需要毒舌" in prompt
    assert "轻度吐槽最多一句" in prompt
    assert "不连轮追着挖苦" in prompt
    assert "先讲道理，再补一句轻松吐槽" not in prompt
    assert "最多一两句锋利吐槽" not in prompt


@pytest.fixture(scope="module")
def reply_strategy_function():
    # 只加载无 IO 的策略方法，以便在没有 AstrBot 服务的环境验证实际注入逻辑。
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AlivePersonaPlugin")
    method = next(node for node in plugin.body if isinstance(node, ast.FunctionDef) and node.name == "_build_reply_strategy")
    namespace = {"re": re, "EmotionSystem": EmotionSystem, "PersonaStyleState": PersonaStyleState}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_build_reply_strategy"]


@pytest.mark.parametrize("message,relation,special", [
    ("这个结论的证据是什么？", "stranger", False),
    ("哈哈又摸鱼了，逗你玩的", "friend", False),
    ("今天很难过，为什么老怼我？", "friend", False),
    ("帮我看看这段逻辑有什么问题", "friend", False),
    ("少废话，闭嘴", "stranger", False),
    ("来点毒舌", "close_friend", True),
])
def test_reply_strategy_injects_tone_without_forced_sarcasm(style, reply_strategy_function, message, relation, special):
    atmosphere = {"mood": "正常"}
    result = decide(style, message, relation, special)
    plugin = SimpleNamespace(
        emotion=EmotionSystem(),
        memory=SimpleNamespace(get_profile=lambda user_id: {"message_count": 20}),
        _reply_char_limit=lambda intent: 120,
    )
    strategy = reply_strategy_function(
        plugin, "user", message, relation, atmosphere,
        style_decision=result, special=special,
    )
    assert f'本轮语气: {result["tone_guidance"]}' in strategy
    assert "最后才加一两句" not in strategy
    assert "先拆逻辑，再轻度毒舌" not in strategy
    if result["intent"] == "emotional":
        assert "先照顾对方情绪" in strategy
        assert "这是网络新知/热词话题" not in strategy
