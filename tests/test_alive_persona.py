import json
from pathlib import Path
import uuid

from a_ju_alive_persona.living_state import LivingState
from a_ju_alive_persona.memory import MemorySystem
from a_ju_alive_persona.persona import PersonaEngine
from a_ju_alive_persona.persona_style import PersonaStyleState
from a_ju_alive_persona.personalization import match_special_user, special_prompt_text
from a_ju_alive_persona.random_behavior import RandomBehavior
_TEST_DATA_ROOT = Path(__file__).resolve().parent / "_tmp"


def fresh_data_dir() -> str:
    _TEST_DATA_ROOT.mkdir(exist_ok=True)
    path = _TEST_DATA_ROOT / uuid.uuid4().hex
    path.mkdir()
    return str(path)


def test_memory_extracts_companion_status_and_social_events():
    memory = MemorySystem(fresh_data_dir())

    summaries = memory.extract_memory_summaries("群友", "我有点累，今晚可能早点睡，谢谢你")
    text = "\n".join(item["summary"] for item in summaries)

    assert "状态不太好" in text
    assert "表达了感谢" in text
    assert memory.should_remember("我有点累，今晚可能早点睡")


def test_memory_extracts_nickname_preference_and_plan():
    memory = MemorySystem(fresh_data_dir())

    summaries = memory.extract_memory_summaries("群友", "我叫小林，我喜欢夜晚，明天得记得带伞")
    text = "\n".join(item["summary"] for item in summaries)

    assert "自我介绍说叫小林" in text
    assert "喜欢夜晚" in text
    assert "希望你记住" in text


def test_special_user_matches_owner_id_name_nickname_and_alias():
    special_users = {
        "群主": {
            "user_id": "1001",
            "nickname": "主人",
            "aliases": ["群主大人"],
            "attitude": "对群主绝对信赖",
        }
    }

    assert match_special_user(special_users, "1001", "别人")["key"] == "群主"
    assert match_special_user(special_users, "2002", "群主大人")["key"] == "群主"
    assert match_special_user(special_users, "2002", "路人", "主人")["key"] == "群主"
    assert match_special_user(special_users, "2002", "路人") is None
    assert "绝对信赖" in special_prompt_text(match_special_user(special_users, "1001", "别人"))

    owner_only = {
        "群主": {
            "user_id": "1001",
            "match_by_id_only": True,
            "nickname": "主人",
            "aliases": ["群主"],
        }
    }
    assert match_special_user(owner_only, "1001", "普通昵称")["key"] == "群主"
    assert match_special_user(owner_only, "2002", "主人") is None


def test_new_users_are_strangers_and_relationship_grows_with_interaction():
    memory = MemorySystem(fresh_data_dir())

    assert memory.get_relation("new-user") == "stranger"
    for _ in range(4):
        memory.update_profile("new-user", nickname="小林")
    assert memory.get_relation("new-user") == "acquaintance"

    for _ in range(16):
        memory.update_profile("new-user", nickname="小林")
    assert memory.get_relation("new-user") == "friend"
    assert memory.get_relation("owner", is_special=True) == "close_friend"


def test_random_behavior_filters_template_tail_and_soft_limits():
    text = "第一点先确认配置，第二点再看完整报错。如果还有问题可以再问我。"
    cleaned = RandomBehavior.clean_reply(text)

    assert "再问我" not in cleaned
    assert "确认配置" in cleaned

    limited = RandomBehavior.soft_limit("第一句很重要。第二句也还行。第三句不该留下。", 12)
    assert limited == "第一句很重要。"


def test_random_behavior_deduplicates_repeated_meaning():
    assert RandomBehavior.deduplicate("知道啦喵。知道啦喵没问题。") == "知道啦喵。"


def test_recent_status_is_structured_and_described():
    memory = MemorySystem(fresh_data_dir())
    memory.remember_from_message("s", "u", "小林", "我今天有点累")

    profile_text = memory.get_profile_description("u")
    assert "ta最近的状态" in profile_text
    assert "状态" in memory.get_recent_status_text("u")


def test_a_ju_fallback_persona_is_used():
    data_dir = fresh_data_dir()
    persona = PersonaEngine(data_dir)

    assert persona.get_name() == "阿橘"
    assert persona.persona.get("profile_id") == "a_ju"
    assert persona.persona["special_users"]["群主"]["user_id"] == "3624487365"
    assert persona.persona["special_users"]["群主"]["match_by_id_only"] is True
    assert persona.persona["special_users"]["群主"]["nickname"] == "小栎主人"
    assert persona.persona.get("mbti_knowledge", {}).get("self_type") == "ISFP（冒险家）"


def test_only_a_ju_persona_file_is_loaded():
    data_dir = fresh_data_dir()
    for filename in ("persona.json", "persona_private.json", "persona_nne_2477.json"):
        with open(f"{data_dir}/{filename}", "w", encoding="utf-8") as file:
            json.dump({"name": "其他角色"}, file, ensure_ascii=False)
    with open(f"{data_dir}/persona_a_ju.json", "w", encoding="utf-8") as file:
        json.dump({"name": "阿橘", "profile_id": "a_ju"}, file, ensure_ascii=False)

    persona = PersonaEngine(data_dir, config={"persona_file": "persona.json"})

    assert persona.get_name() == "阿橘"
    assert persona.persona.get("profile_id") == "a_ju"
    assert persona.loaded_from.endswith("persona_a_ju.json")


def test_system_prompt_contains_relationship_layers_and_mbti_knowledge():
    persona = PersonaEngine(fresh_data_dir())
    prompt = persona.build_system_prompt("")

    assert "软萌小骄傲" in prompt
    assert "群主：绝对信赖" in prompt
    assert "熟悉群友" in prompt
    assert "ISFP（冒险家）" in prompt
    assert "不能把 MBTI 当诊断" in prompt


def test_living_state_light_reply_skips_requests_and_owner():
    state = LivingState()
    state._random = lambda chance: True
    atmosphere = {"mood": "热闹"}

    assert not state.should_light_reply("怎么判断MBTI呀", "stranger", atmosphere, False, 1.0)
    assert not state.should_light_reply("随便说句话", "stranger", atmosphere, True, 1.0)
    assert state.should_light_reply("随便说句话", "stranger", atmosphere, False, 1.0)


def test_persona_style_has_mbti_specific_mode():
    style = PersonaStyleState(trait_anchor_rate=0.0)
    decision = style.decide("s", "我是INTJ，你觉得怎么样", "stranger", {"mood": "正常"}, False)

    assert decision["intent"] == "mbti"
    assert "MBTI" in decision["mode"]


def test_persona_style_allows_identity_only_when_asked():
    style = PersonaStyleState(trait_anchor_rate=1.0, identity_mention_policy="never")

    assert style.decide("s1", "你是谁", "stranger", {"mood": "正常"}, False)["allow_identity_mention"]
    assert not style.decide("s2", "今天天气不错", "stranger", {"mood": "正常"}, False)["allow_identity_mention"]


def test_dedicated_plugin_has_no_external_bridge_module_or_switch():
    plugin_dir = Path(__file__).resolve().parents[1]

    assert not (plugin_dir / "bridge.py").exists()
    schema = (plugin_dir / "_conf_schema.json").read_text(encoding="utf-8")
    assert "bridge_enabled" not in schema
    assert "bridge_allowed_user_id" not in schema
    assert '"default": "3624487365"' in schema
    assert '"default": "小栎主人"' in schema





