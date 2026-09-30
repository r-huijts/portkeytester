import unittest
from unittest.mock import patch, MagicMock
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_portkey as tp


class TestInterpretVideoPollPayload(unittest.TestCase):
    def test_pending(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({"status": "pending", "id": "gen-vid-1"}),
            "pending",
        )

    def test_completed_with_urls(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({
                "status": "completed",
                "unsigned_urls": ["https://example.com/v.mp4"],
            }),
            "completed",
        )

    def test_completed_without_urls(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({"status": "completed", "unsigned_urls": []}),
            "completed_no_urls",
        )

    def test_failed_statuses(self):
        for status in ("failed", "error", "cancelled", "expired"):
            self.assertEqual(
                tp.interpret_video_poll_payload({"status": status}),
                "failed",
            )

    def test_in_progress_is_pending(self):
        self.assertEqual(
            tp.interpret_video_poll_payload({"status": "in_progress", "id": "gen-vid-1"}),
            "pending",
        )


class TestPortkeyVideoRequest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_create_posts_to_videos_root(self, mock_urlopen):
        body = {"id": "gen-vid-abc", "status": "pending"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            provider="@openroutervideomodels",
            model="kwaivgi/kling-v3.0-std",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "gen-vid-abc")

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.portkey.ai/v1/videos")
        self.assertEqual(req.get_header("X-portkey-api-key"), "pk-test")
        self.assertEqual(req.get_header("X-portkey-provider"), "@openroutervideomodels")
        self.assertEqual(req.get_header("User-agent"), "portkey-tester/1.0")
        self.assertEqual(req.get_method(), "POST")

    @patch("urllib.request.urlopen")
    def test_poll_gets_videos_id(self, mock_urlopen):
        body = {"status": "pending", "id": "gen-vid-abc"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            provider="@openroutervideomodels",
            model="kwaivgi/kling-v3.0-std",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
            video_id="gen-vid-abc",
        )
        self.assertEqual(status, 200)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://api.portkey.ai/v1/videos/gen-vid-abc",
        )
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)


class TestVideoGeneration(unittest.TestCase):
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_then_poll_until_completed(self, mock_req, _sleep):
        mock_req.side_effect = [
            (200, {"id": "gen-vid-1", "status": "pending"}),
            (200, {"status": "pending", "id": "gen-vid-1"}),
            (200, {
                "status": "completed",
                "id": "gen-vid-1",
                "unsigned_urls": ["https://example.com/v"],
                "usage": {"cost": 0.63},
            }),
        ]
        ok, details = tp.test_video_generation(
            api_key="pk",
            provider="@openroutervideomodels",
            model_slug="kwaivgi/kling-v3.0-std",
        )
        self.assertTrue(ok)
        self.assertEqual(details["endpoint"], "video")
        self.assertEqual(details["unsigned_urls"], ["https://example.com/v"])
        self.assertEqual(details["cost"], 0.63)
        self.assertEqual(mock_req.call_count, 3)

    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_missing_id_fails(self, mock_req, _sleep):
        mock_req.return_value = (200, {"status": "pending"})
        ok, details = tp.test_video_generation("pk", "@prov", "model")
        self.assertFalse(ok)
        self.assertIn("error", details)

    @patch("test_portkey.VIDEO_POLL_TIMEOUT_SEC", 0.0)
    @patch("test_portkey.VIDEO_POLL_INTERVAL_SEC", 0.0)
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_timeout(self, mock_req, _sleep):
        def side_effect(api_key, provider, model, prompt, video_id=None):
            return 200, {"id": "gen-vid-1", "status": "pending"}

        mock_req.side_effect = side_effect
        ok, details = tp.test_video_generation("pk", "@prov", "model")
        self.assertFalse(ok)
        self.assertIn("timeout", str(details.get("error", "")).lower())


if __name__ == "__main__":
    unittest.main()
