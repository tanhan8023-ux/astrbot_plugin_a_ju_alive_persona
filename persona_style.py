"""人设显性锚点、情境语气与冷却策略。"""
import re
import time


class PersonaStyleState:
    def __init__(self, trait_anchor_rate: float = 0.35, identity_mention_policy: str = 'rare'):
        self.trait_anchor_rate = trait_anchor_rate
        self.identity_mention_policy = identity_mention_policy
        self.last_anchor_by_session: dict[str, float] = {}
        self.catchphrase_cooldown_until: dict[str, float] = {}
        self.last_mode_by_session: dict[str, str] = {}

    def decide(self, session_id: str, message: str, relation: str, atmosphere: dict, special: bool) -> dict:
        intent = self._classify_intent(message)
        now = time.time()
        recently_anchored = now - self.last_anchor_by_session.get(session_id, 0) < 180

        rate = self.trait_anchor_rate
        if intent == 'technical':
            rate *= 0.35
        elif intent == 'mbti':
            rate *= 1.05
        elif intent == 'emotional':
            rate *= 0.75
        elif intent == 'casual':
            rate *= 1.1
        if relation in ('friend', 'close_friend') or special:
            rate += 0.08
        if atmosphere.get('mood') == '热闹':
            rate *= 0.65
        if recently_anchored:
            rate *= 0.35

        anchor = self._random(max(0.02, min(0.85, rate)))
        if anchor:
            self.last_anchor_by_session[session_id] = now

        mode = self._mode(intent, anchor, special, relation)
        tone, tone_guidance = self._decide_tone(message, intent, relation, special)
        self.last_mode_by_session[session_id] = mode

        return {
            'intent': intent,
            'anchor': anchor,
            'mode': mode,
            'tone': tone,
            'tone_guidance': tone_guidance,
            'allow_identity_mention': self._allow_identity_mention(message, anchor),
            'catchphrase_on_cooldown': self.catchphrase_on_cooldown(session_id),
        }

    def catchphrase_on_cooldown(self, session_id: str) -> bool:
        return time.time() < self.catchphrase_cooldown_until.get(session_id, 0)

    def mark_catchphrase(self, session_id: str, cooldown_seconds: int = 240):
        self.catchphrase_cooldown_until[session_id] = time.time() + cooldown_seconds

    def get_last_mode(self, session_id: str) -> str:
        return self.last_mode_by_session.get(session_id, '自然')

    @staticmethod
    def _classify_intent(message: str) -> str:
        # 先接住低落、歉意与不想被调侃的信号，避免被‘为什么/今天/是不是’抢走。
        if PersonaStyleState._needs_gentle_tone(message):
            return 'emotional'
        if re.search(r'(mbti|16型|人格类型|[ei][ns][tf][jp])', message, re.I):
            return 'mbti'
        if re.search(r'(新梗|梗|热梗|热词|流行语|网络用语|网络文化|上网冲浪|新知识|新概念|最近流行|最近大家|刚出来|刚发布|新出的|最新研究|新发现|科普|热点|热搜|时事|新闻|头条|最新|今天|今日|刚刚|近期|本周|政策|发布会|辟谣|股市|行情|选举|战争|地震|台风|赛事|比赛结果|news|latest|today|current)', message, re.I):
            return 'current_affairs'
        if re.search(r'(逻辑|反驳|怼|双标|偷换概念|自相矛盾|因果倒置|以偏概全|证据|依据|合理吗|凭什么|怎么证明|怎么看|是不是)', message, re.I):
            return 'logic'
        if re.search(r'(怎么|如何|为什么|配置|api|url|/v1|密钥|模型|报错|错误|帮|求|教)', message, re.I):
            return 'technical'
        if re.search(r'(累|困|不舒服|难受|难过|烦|焦虑|崩溃|委屈|压力|开心|谢谢|感谢|对不起|抱歉)', message):
            return 'emotional'
        if re.search(r'(早|晚安|睡了|走了|拜|回来了)', message):
            return 'social'
        return 'casual'

    @staticmethod
    def _mode(intent: str, anchor: bool, special: bool, relation: str) -> str:
        if intent == 'technical':
            return '答题优先，低显性人设'
        if intent == 'logic':
            return '先温和拆逻辑，轻度毒舌按情境可选，不攻击人格'
        if intent == 'current_affairs':
            return '先核对日期与来源，再解释网络新知或热词'
        if intent == 'mbti':
            return '轻松聊MBTI，给倾向但避免刻板定型'
        if intent == 'emotional':
            return '接情绪，少解释设定'
        if special or relation in ('friend', 'close_friend'):
            return '熟人自然，语气贴合'
        if anchor:
            return '轻微显性人设'
        return '自然低显性'

    @staticmethod
    def _needs_gentle_tone(message: str) -> bool:
        return bool(re.search(
            r'(累了|好累|很累|太累|有点累|困了|好困|很困|太困|有点困|不舒服|难受|'
            r'难过|伤心|焦虑|崩溃|委屈|压力(?:大|太|很|好|有点)|害怕|失落|痛苦|'
            r'心情不好|抑郁|孤独|撑不住|活不下去|不想活|想死|自杀|被骂|被欺负|'
            r'生病|去世|失恋|对不起|抱歉|认错|道歉|(?<!麻)烦(?!琐)|不开心|受不了|'
            r'我(?:就是|是)(?:个)?(?:废物|垃圾)|我是不是(?:很|太)?没用|一无是处|'
            r'(?:别|不要|不想|不喜欢).{0,8}(?:毒舌|吐槽|挖苦|调侃|嘲讽|讽刺|阴阳怪气|开玩笑|怼|笑我)|'
            r'(?:为什么|干嘛|怎么|为何).{0,8}(?:怼我|损我|嘲讽我|讽刺我|挖苦我|笑我)|'
            r'认真(?:点|一点|说)|正经(?:点|一点|说)|不是开玩笑|不好笑|别闹|别拿我开涮)',
            message,
        ))

    @staticmethod
    def _decide_tone(message: str, intent: str, relation: str, special: bool) -> tuple[str, str]:
        # 这是语气建议，不凭一个‘逻辑/双标’关键词就要求模型攻击对方。
        if special:
            return 'gentle', '对小栎主人保持温柔暖心；需要纠正时也耐心讲理由，不用毒舌顶嘴'
        if PersonaStyleState._needs_gentle_tone(message) or intent == 'emotional':
            return 'gentle', '本轮不毒舌、不补刀；先体谅对方，认真接住情绪、歉意或停止玩笑的意愿，需要帮助时温和给出关键答案'
        if re.search(
            r'((?:来|请|尽管|随便|可以|想听你|帮我)(?:吐槽|调侃|怼|损)我|'
            r'(?:^|[，,。！!；;\s])(?:你)?(?:吐槽|调侃|怼|损)我(?:一下|两句|几句|吧|嘛|呀|啊)|'
            r'(?:来点|来一点|说点)毒舌|开个玩笑)',
            message,
        ):
            return 'playful', '对方愿意轻松开玩笑，可以可选地轻轻吐槽一句；只调侃小事或说法，不攻击人格，别连续挖苦'
        if intent == 'technical' or re.search(r'(求助|请教|帮我|帮忙|教我|求你|求求|怎么办)', message):
            return 'gentle', '对方在认真求助，本轮不毒舌、不笑话失误；先耐心给出有用的回答'
        if relation in ('friend', 'close_friend') and re.search(r'(哈哈|嘿嘿|笑死|互损|斗嘴|逗你|开玩笑|闹着玩)', message):
            return 'playful', '熟人正在轻松玩笑，可选地接一句温和的小吐槽，不强行毒舌；结合最近上下文确认对方也乐意，对方不舒服就收住'
        if re.search(r'(闭嘴|滚开|少废话|别装|你(?:就是|是)(?:个)?(?:垃圾|废物|蠢货)|反复双标|又双标|还在双标|一再双标|还在偷换概念)', message):
            return 'firm', '如果结合上下文确实是在挑衅或反复双标，可以坚定设界限、指出具体问题，最多一句轻度吐槽；不辱骂、不升级争吵，不把引用或求助误当攻击'
        return 'gentle', '以温和友善为主，普通分歧先讲理由，不默认补吐槽；是否适合轻轻调侃要结合最近上下文与对方意愿，拿不准就温和'

    def _allow_identity_mention(self, message: str, anchor: bool) -> bool:
        if re.search(r'(你是谁|你叫|身份|设定|背景|是什么人)', message):
            return True
        if self.identity_mention_policy == 'never':
            return False
        if self.identity_mention_policy == 'rare':
            return anchor and self._random(0.15)
        return anchor

    @staticmethod
    def _random(chance: float) -> bool:
        return (time.time_ns() % 10000) / 10000 < chance


