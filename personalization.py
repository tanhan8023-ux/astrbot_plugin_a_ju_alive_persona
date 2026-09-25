"""个性化关系工具。"""


def match_special_user(special_users: dict, user_id: str, user_name: str, nickname: str = None):
    if not special_users:
        return None

    candidates = {
        str(user_id or '').strip(),
        str(user_name or '').strip(),
        str(nickname or '').strip(),
    }
    candidates = {c for c in candidates if c}

    for key, info in special_users.items():
        configured_user_id = str(info.get('user_id') or '').strip()
        if info.get('match_by_id_only') and configured_user_id:
            if str(user_id or '').strip() == configured_user_id:
                return {'key': key, 'info': info}
            continue

        ids = {
            str(key or '').strip(),
            configured_user_id,
            str(info.get('nickname') or '').strip(),
        }
        aliases = info.get('aliases') or []
        ids.update(str(alias or '').strip() for alias in aliases)
        ids = {x for x in ids if x}
        if candidates & ids:
            return {'key': key, 'info': info}
    return None


def special_prompt_text(special) -> str:
    if not special:
        return ''
    info = special['info']
    parts = []
    if info.get('attitude'):
        parts.append(info['attitude'])
    if info.get('nickname'):
        parts.append(f'你称呼ta为"{info["nickname"]}"')
    return '。'.join(parts)

