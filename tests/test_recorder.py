import os
from pathlib import Path
import unittest
from unittest.mock import patch

import recorder


class CommandTests(unittest.TestCase):
    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav"}, clear=True)
    def test_both_streams_and_hour_segments(self):
        args = recorder.command(Path("/recordings"))
        self.assertEqual(args.count("-i"), 2)
        self.assertEqual(args[args.index("-segment_time") + 1], "3600")
        self.assertIn("0:v:0", args)
        self.assertIn("1:a:0", args)
        self.assertIn("matroska", args)
        self.assertNotEqual(args[-1], recorder.command(Path("/recordings"))[-1])

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav",
                             "SEGMENT_SECONDS": "0"}, clear=True)
    def test_reject_invalid_segment_length(self):
        with self.assertRaises(ValueError):
            recorder.command(Path("/recordings"))


if __name__ == "__main__":
    unittest.main()
