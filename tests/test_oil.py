"""Regression coverage for the oil provider's User-Agent check."""

import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.oil.client import fetch_oil_data


class OilClientTests(unittest.TestCase):
    def test_provider_requires_browser_user_agent(self):
        data = {"name": "河南", "p92": "8.62", "date": "2026-10-28"}

        def provider(url, **kwargs):
            response = Mock()
            if not kwargs.get("headers", {}).get("User-Agent", "").startswith("Mozilla/"):
                response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
            response.json.return_value = {"status": 1, "data": data}
            return response

        with patch("plugin.features.oil.client.requests.get", side_effect=provider) as get:
            self.assertEqual(fetch_oil_data("河南"), data)
        self.assertEqual(get.call_args.kwargs["params"], {"area": "河南"})
        self.assertEqual(get.call_args.kwargs["timeout"], 10)
