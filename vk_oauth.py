import re
from urllib.parse import parse_qs, urlsplit


OAUTH_REDIRECT_HOSTS = {'api.vk.com', 'oauth.vk.com', 'oauth.vk.ru'}


def parse_oauth_token(value):
    try:
        candidates = re.findall(r'https://[^\s]+', value)
    except (TypeError, ValueError):
        return None

    for matched_candidate in candidates:
        for candidate in (matched_candidate, matched_candidate.rstrip('.,;:!?)]}>')):
            try:
                url = urlsplit(candidate)
            except ValueError:
                continue
            if url.hostname not in OAUTH_REDIRECT_HOSTS or url.path != '/blank.html':
                continue

            params = parse_qs(url.fragment, keep_blank_values=True)
            tokens = params.get('access_token', [])
            user_ids = params.get('user_id', [])
            if len(tokens) != 1 or not tokens[0]:
                continue
            if len(user_ids) != 1 or not user_ids[0].isdigit():
                continue
            return tokens[0]
    return None
