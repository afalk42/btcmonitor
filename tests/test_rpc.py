import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from btcmonitor.rpc import BitcoinRPC, RPCConfig, RPCError


def basic(credentials):
    return "Basic " + base64.b64encode(credentials.encode()).decode()


class FakeNode:
    """Stands in for requests.post: accepts only the credentials in `accepted`"""

    def __init__(self, accepted):
        self.accepted = accepted
        self.calls = 0

    def __call__(self, url, headers, data, timeout):
        self.calls += 1
        response = Mock()
        if headers.get("Authorization") == basic(self.accepted):
            response.status_code = 200
            response.json.return_value = {"result": "ok", "error": None}
        else:
            response.status_code = 401
        return response


class CookieAuthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.datadir = Path(tmp.name)
        self.cookie = self.datadir / ".cookie"

    def rpc(self, **kwargs):
        return BitcoinRPC(RPCConfig(datadir=self.datadir, **kwargs))

    def test_new_cookie_after_bitcoind_restart_is_picked_up(self):
        self.cookie.write_text("__cookie__:first")
        rpc = self.rpc()
        with patch("btcmonitor.rpc.requests.post", FakeNode("__cookie__:first")):
            self.assertEqual(rpc.call("getblockcount"), "ok")
        self.cookie.write_text("__cookie__:second")  # bitcoind restarted
        node = FakeNode("__cookie__:second")
        with patch("btcmonitor.rpc.requests.post", node):
            self.assertEqual(rpc.call("getblockcount"), "ok")
            self.assertEqual(rpc.call("getblockcount"), "ok")
        self.assertEqual(node.calls, 3)  # one retry, then the new cookie is used directly

    def test_cookie_created_after_startup_is_picked_up(self):
        rpc = self.rpc()
        self.cookie.write_text("__cookie__:late")
        with patch("btcmonitor.rpc.requests.post", FakeNode("__cookie__:late")):
            self.assertEqual(rpc.call("getblockcount"), "ok")

    def test_rejected_password_falls_back_to_cookie(self):
        self.cookie.write_text("__cookie__:abc")
        rpc = self.rpc(user="alice", password="wrong")
        with patch("btcmonitor.rpc.requests.post", FakeNode("__cookie__:abc")):
            self.assertEqual(rpc.call("getblockcount"), "ok")

    def test_unchanged_rejected_cookie_is_not_retried(self):
        self.cookie.write_text("__cookie__:stale")
        rpc = self.rpc()
        node = FakeNode("__cookie__:other")
        with patch("btcmonitor.rpc.requests.post", node):
            with self.assertRaisesRegex(RPCError, "Unauthorized"):
                rpc.call("getblockcount")
        self.assertEqual(node.calls, 1)



class ResponseParsingTests(unittest.TestCase):
    def call_with_response(self, **attrs):
        response = Mock(status_code=200, **attrs)
        rpc = BitcoinRPC(RPCConfig(user="u", password="p"))
        with patch("btcmonitor.rpc.requests.post", return_value=response):
            return rpc.call("getblockcount")

    def test_non_json_body_raises_rpc_error(self):
        with self.assertRaisesRegex(RPCError, "Invalid JSON"):
            self.call_with_response(text="<html>proxy error</html>", json=Mock(side_effect=ValueError("no JSON")))

    def test_non_object_json_raises_rpc_error(self):
        with self.assertRaisesRegex(RPCError, "Unexpected JSON-RPC response"):
            self.call_with_response(json=Mock(return_value=[1, 2]))


if __name__ == "__main__":
    unittest.main()
