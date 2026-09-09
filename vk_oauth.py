import json
import re
from urllib.parse import parse_qs, unquote_plus, urlsplit


OAUTH_REDIRECT_LINK = re.compile(
    r'https://(?:(?:oauth|api)\.vk\.com|oauth\.vk\.ru)/blank\.html#[^\s]+'
)


def parse_oauth_token(value):
    try:
        match = OAUTH_REDIRECT_LINK.search(value)
    except TypeError:
        return None
    if not match:
        return None

    matched_candidate = match.group(0)
    for candidate in (matched_candidate, matched_candidate.rstrip('.,;:!?)]}>')):
        try:
            url = urlsplit(candidate)
        except ValueError:
            continue

        if url.fragment.startswith('payload='):
            try:
                payload = json.loads(unquote_plus(url.fragment[len('payload='):]))
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            user = payload.get('user', {})
            token = payload.get('token')
            ttl = payload.get('ttl')
            user_id = user.get('id') if isinstance(user, dict) else None
            if payload.get('type') != 'silent_token':
                continue
            if not isinstance(token, str) or not token:
                continue
            if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
                continue
            if not isinstance(user_id, int) or isinstance(user_id, bool):
                continue
            return token

        params = parse_qs(url.fragment, keep_blank_values=True)
        tokens = params.get('access_token', [])
        user_ids = params.get('user_id', [])
        if len(tokens) != 1 or not tokens[0]:
            continue
        if len(user_ids) != 1 or not user_ids[0].isdigit():
            continue
        return tokens[0]
    return None
