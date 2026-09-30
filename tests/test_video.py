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
        for status in ("failed", "error", "cancelled"):
            self.assertEqual(
                tp.interpret_video_poll_payload({"status": status}),
                "failed",
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
        self.assertEqual(req.get_method(), "POST")

    @patch("urllib.request.urlopen")
    def test_poll_posts_to_videos_id(self, mock_urlopen):
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


if __name__ == "__main__":
    unittest.main()
