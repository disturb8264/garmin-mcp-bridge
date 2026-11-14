import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gateway.app import load_config, validate_upstream_url


class UpstreamURLTests(unittest.TestCase):
    def test_existing_urls(self):
        for url in (
            "http://127.0.0.1:18765/mcp",
            "http://localhost:18766/mcp",
            "https://mcp.example.net/mcp",
        ):
            with self.subTest(url=url):
                validate_upstream_url(url)

    def test_private_http_requires_opt_in(self):
        for url in (
            "http://10.1.2.3:8767/mcp",
            "http://172.17.0.9:8767/mcp",
            "http://192.168.100.12:8767/mcp",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_upstream_url(url)
                validate_upstream_url(url, True)

    def test_other_http_stays_rejected(self):
        for url in (
            "http://8.8.8.8:8767/mcp",
            "http://169.254.1.2:8767/mcp",
            "http://mcp.example.net/mcp",
            "http://[::1]:8767/mcp",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_upstream_url(url, True)

    def test_malformed_urls(self):
        for url in (
            "ftp://192.168.100.12/mcp",
            "http://192.168.100.12:bad/mcp",
            "http://user:pass@192.168.100.12/mcp",
            "http://192.168.100.12/mcp#fragment",
            "http://192.168.100.12",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_upstream_url(url, True)

    def test_config_opt_in(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token"
            token.write_text("x" * 32, encoding="ascii")
            token.chmod(0o600)
            config = root / "gateway.yaml"
            content = (
                "gateway_token_file: token\n"
                "upstreams:\n"
                "  - id: echo\n"
                "    url: http://192.168.100.12:8767/mcp\n"
                "    token_file: token\n"
                "    allowed_tools: [echo]\n"
            )
            config.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config)
            config.write_text(content + "    allow_private_http: true\n", encoding="utf-8")
            _, upstreams, _ = load_config(config)
            self.assertEqual(upstreams[0].url, "http://192.168.100.12:8767/mcp")


if __name__ == "__main__":
    unittest.main()
