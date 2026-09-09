import re
from urllib.parse import parse_qs, urlsplit


OAUTH_REDIRECT_LINK = re.compile(
    r'https://(?:oauth|api)\.vk\.(?:com|ru)/blank\.html#[^\s]+'
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

        params = parse_qs(url.fragment, keep_blank_values=True)
        tokens = params.get('access_token', [])
        user_ids = params.get('user_id', [])
        if len(tokens) != 1 or not tokens[0]:
            continue
        if len(user_ids) != 1 or not user_ids[0].isdigit():
            continue
        return tokens[0]
    return None
