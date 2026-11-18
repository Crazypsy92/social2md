import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from douyin2txt import process_video


class ProcessVideoSafetyTests(unittest.TestCase):
    def test_empty_transcript_does_not_delete_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "demo_video.mp4"
            wav = root / "audio.wav"
            output = root / "output"
            video.write_bytes(b"fake-video")
            wav.write_bytes(b"fake-wav")

            with (
                patch("douyin2txt.read_desc", return_value=""),
                patch("douyin2txt.extract_audio", return_value=wav),
                patch("douyin2txt.transcribe", return_value=([], {"avg_logprob": 0.0})),
                patch("douyin2txt.format_transcript", return_value=""),
            ):
                status, _ = process_video(
                    video,
                    output,
                    set(),
                    "small",
                    "zh",
                    delete_video=True,
                    force=False,
                    require_transcript=True,
                )

            self.assertEqual(status, "fail")
            self.assertTrue(video.exists())
            self.assertFalse((output / "demo.md").exists())
            self.assertFalse(wav.exists())


if __name__ == "__main__":
    unittest.main()
