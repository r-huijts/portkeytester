import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
from datetime import datetime
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


class TestGetVideoRoute(unittest.TestCase):
    def test_known_route(self):
        self.assertEqual(tp.get_video_route("veo"), "veo")
        cfg = tp.get_video_route_config("veo")
        self.assertEqual(cfg["route"], "veo")
        self.assertEqual(cfg["provider"], "@openroutervideomodels")
        self.assertEqual(cfg["model"], "google/veo-3.1-fast")

    def test_unknown_route_raises(self):
        with self.assertRaises(ValueError) as ctx:
            tp.get_video_route("unknown-model")
        self.assertIn("No video route configured", str(ctx.exception))


class TestPortkeyVideoRequest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_create_sends_provider_and_metadata(self, mock_urlopen):
        body = {"id": "gen-vid-abc", "status": "pending"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            video_route="veo",
            provider="@openroutervideomodels",
            model="google/veo-3.1-fast",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
            config_id="cfg-123",
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "gen-vid-abc")

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.portkey.ai/v1/proxy/videos")
        self.assertEqual(req.get_header("X-portkey-api-key"), "pk-test")
        self.assertEqual(req.get_header("X-portkey-config"), "cfg-123")
        self.assertEqual(req.get_header("X-portkey-provider"), "@openroutervideomodels")
        meta = json.loads(req.get_header("X-portkey-metadata"))
        self.assertEqual(meta, {"video_route": "veo"})
        self.assertEqual(req.get_method(), "POST")
        payload = json.loads(req.data.decode())
        self.assertEqual(payload["model"], "google/veo-3.1-fast")

    @patch("urllib.request.urlopen")
    def test_poll_gets_videos_id_with_metadata(self, mock_urlopen):
        body = {"status": "pending", "id": "gen-vid-abc"}
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        status, data = tp.portkey_video_request(
            api_key="pk-test",
            video_route="veo",
            provider="@openroutervideomodels",
            model="google/veo-3.1-fast",
            prompt=tp.VIDEO_SAMPLE_PROMPT,
            video_id="gen-vid-abc",
        )
        self.assertEqual(status, 200)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://api.portkey.ai/v1/proxy/videos/gen-vid-abc",
        )
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        meta = json.loads(req.get_header("X-portkey-metadata"))
        self.assertEqual(meta, {"video_route": "veo"})
        self.assertEqual(req.get_header("X-portkey-provider"), "@openroutervideomodels")


class TestVideoGeneration(unittest.TestCase):
    @patch("test_portkey.download_portkey_video")
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_then_poll_until_completed(self, mock_req, _sleep, mock_dl):
        mock_req.side_effect = [
            (200, {"id": "gen-vid-1", "status": "pending"}),
            (200, {"status": "pending", "id": "gen-vid-1"}),
            (200, {
                "status": "completed",
                "id": "gen-vid-1",
                "unsigned_urls": ["https://openrouter.ai/api/v1/videos/gen-vid-1/content?index=0"],
                "usage": {"cost": 0.63},
            }),
        ]
        mock_dl.return_value = (True, "/tmp/portkey-video-gen-vid-1-0.mp4")
        ok, details = tp.test_video_generation(
            api_key="pk",
            model_slug="veo",
            config_id="cfg-1",
        )
        self.assertTrue(ok)
        self.assertEqual(details["endpoint"], "video")
        self.assertEqual(details["video_route"], "veo")
        self.assertEqual(details["provider"], "@openroutervideomodels")
        self.assertEqual(details["request_model"], "google/veo-3.1-fast")
        self.assertEqual(mock_req.call_count, 3)
        mock_dl.assert_called_once()
        create_kwargs = mock_req.call_args_list[0].kwargs
        self.assertEqual(create_kwargs["video_route"], "veo")
        self.assertEqual(create_kwargs["provider"], "@openroutervideomodels")
        self.assertEqual(create_kwargs["model"], "google/veo-3.1-fast")
        self.assertEqual(create_kwargs["config_id"], "cfg-1")
        self.assertEqual(mock_dl.call_args.kwargs["provider"], "@openroutervideomodels")

    @patch("test_portkey.download_portkey_video")
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_custom_prompt_passed_to_create(self, mock_req, _sleep, mock_dl):
        mock_req.side_effect = [
            (200, {"id": "gen-vid-1", "status": "pending"}),
            (200, {
                "status": "completed",
                "id": "gen-vid-1",
                "unsigned_urls": ["https://openrouter.ai/x"],
            }),
        ]
        mock_dl.return_value = (True, "/tmp/out.mp4")
        custom = "a rubber duck winning a hackathon"
        ok, details = tp.test_video_generation(
            api_key="pk",
            model_slug="veo",
            prompt=custom,
        )
        self.assertTrue(ok)
        self.assertEqual(details["prompt"], custom)
        self.assertEqual(mock_req.call_args_list[0].kwargs["prompt"], custom)

    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_create_missing_id_fails(self, mock_req, _sleep):
        mock_req.return_value = (200, {"status": "pending"})
        ok, details = tp.test_video_generation(api_key="pk", model_slug="veo")
        self.assertFalse(ok)
        self.assertIn("error", details)

    def test_unknown_model_slug_raises(self):
        with self.assertRaises(ValueError):
            tp.test_video_generation(api_key="pk", model_slug="not-a-route")

    @patch("test_portkey.VIDEO_POLL_TIMEOUT_SEC", 0.0)
    @patch("test_portkey.VIDEO_POLL_INTERVAL_SEC", 0.0)
    @patch("test_portkey.time.sleep", return_value=None)
    @patch("test_portkey.portkey_video_request")
    def test_timeout(self, mock_req, _sleep):
        def side_effect(api_key, video_route, provider, model, prompt, video_id=None, config_id=None):
            return 200, {"id": "gen-vid-1", "status": "pending"}

        mock_req.side_effect = side_effect
        ok, details = tp.test_video_generation(api_key="pk", model_slug="veo")
        self.assertFalse(ok)
        self.assertIn("timeout", str(details.get("error", "")).lower())


class TestPortkeyVideoContentUrl(unittest.TestCase):
    def test_builds_portkey_url(self):
        self.assertEqual(
            tp.portkey_video_content_url("gen-vid-1", 0),
            "https://api.portkey.ai/v1/proxy/videos/gen-vid-1/content?index=0",
        )


class TestVideoSavePath(unittest.TestCase):
    def test_includes_datetime_and_model_slug(self):
        when = datetime(2026, 9, 30, 13, 45, 12)
        path = tp.video_save_path("kwaivgi/kling-v3.0-std", when=when)
        self.assertTrue(path.endswith(
            os.path.join("video", "portkey-video-20260930-134512-kwaivgi_kling-v3.0-std.mp4")
        ))
        self.assertTrue(os.path.isdir(os.path.dirname(path)))

    def test_index_suffix_for_extra_outputs(self):
        when = datetime(2026, 9, 30, 13, 45, 12)
        path = tp.video_save_path("model", index=2, when=when)
        self.assertTrue(path.endswith(
            os.path.join("video", "portkey-video-20260930-134512-model-2.mp4")
        ))


class TestVideoWaitStatus(unittest.TestCase):
    def test_rotates_and_omits_job_id(self):
        msg0 = tp._video_wait_status(0, "pending", 12)
        msg1 = tp._video_wait_status(1, "in_progress", 17)
        self.assertNotEqual(msg0, msg1)
        self.assertIn("pending", msg0)
        self.assertIn("12s", msg0)
        self.assertNotIn("gen-vid", msg0)
        self.assertNotIn("gen-vid", msg1)


if __name__ == "__main__":
    unittest.main()
