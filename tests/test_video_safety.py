import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from social2md_app.video import process_video


class VideoSafetyTests(unittest.TestCase):
    def test_empty_transcript_does_not_delete_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "demo_video.mp4"
            wav = root / "audio.wav"
            output = root / "output"
            video.write_bytes(b"fake-video")
            wav.write_bytes(b"fake-wav")

            with (
                patch("social2md_app.video.read_desc", return_value=""),
                patch("social2md_app.video.extract_audio", return_value=wav),
                patch("social2md_app.video.transcribe", return_value=([], {"avg_logprob": 0.0})),
                patch("social2md_app.video.format_transcript", return_value=""),
            ):
                status, _ = process_video(
                    video, output, set(), "small", "zh",
                    delete_video=False, force=True, require_transcript=True,
                )

            self.assertEqual(status, "fail")
            self.assertTrue(video.exists())
            self.assertFalse((output / "demo.md").exists())
            self.assertFalse(wav.exists())


if __name__ == "__main__":
    unittest.main()
