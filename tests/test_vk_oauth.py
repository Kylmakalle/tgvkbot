import unittest

from vk_oauth import parse_oauth_token


class ParseOauthTokenTest(unittest.TestCase):
    def test_parses_vk_ru_redirect_without_expiration(self):
        url = (
            'https://oauth.vk.ru/blank.html'
            '#access_token=vk1.a.9sSv_ABC-123&user_id=123456789'
        )

        self.assertEqual(parse_oauth_token(url), 'vk1.a.9sSv_ABC-123')

    def test_parses_legacy_redirect_with_expiration(self):
        url = (
            'https://oauth.vk.com/blank.html'
            '#access_token=legacy.token&expires_in=0&user_id=123456789'
        )

        self.assertEqual(parse_oauth_token(url), 'legacy.token')

    def test_parses_fragment_parameters_in_any_order(self):
        url = (
            'https://oauth.vk.ru/blank.html'
            '#user_id=123456789&state=login&access_token=vk1.a.token'
        )

        self.assertEqual(parse_oauth_token(url), 'vk1.a.token')

    def test_parses_redirect_in_surrounding_text(self):
        text = (
            'VK redirect: https://oauth.vk.ru/blank.html'
            '#access_token=vk1.a.token&user_id=123456789.'
        )

        self.assertEqual(parse_oauth_token(text), 'vk1.a.token')

    def test_rejects_untrusted_redirect(self):
        url = (
            'https://oauth.vk.ru.example.com/blank.html'
            '#access_token=vk1.a.token&user_id=123456789'
        )

        self.assertIsNone(parse_oauth_token(url))


if __name__ == '__main__':
    unittest.main()
