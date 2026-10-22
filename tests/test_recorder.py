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
        self.assertEqual(args[args.index("-segment_atclocktime") + 1], "1")
        self.assertEqual(args[args.index("-force_key_frames") + 1], "expr:gte(t,n_forced*1)")
        self.assertIn("0:v:0", args)
        self.assertIn("1:a:0", args)
        self.assertIn("matroska", args)
        self.assertEqual(args[args.index("-crf") + 1], "28")
        self.assertEqual(args[args.index("-preset") + 1], "veryfast")
        self.assertNotEqual(args[-1], recorder.command(Path("/recordings"))[-1])

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav"}, clear=True)
    def test_configurable_compression(self):
        for value in ("0", "23", "28", "30", "51"):
            with self.subTest(value=value), patch.dict(os.environ, {"VIDEO_CRF": value}):
                args = recorder.command(Path("/recordings"))
                self.assertEqual(args[args.index("-crf") + 1], value)
        for value in ("-1", "52", "nan", "28.5", ""):
            with self.subTest(value=value), patch.dict(os.environ, {"VIDEO_CRF": value}):
                with self.assertRaises(ValueError):
                    recorder.command(Path("/recordings"))

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav",
                             "SEGMENT_SECONDS": "60"}, clear=True)
    def test_clock_aligned_custom_interval(self):
        args = recorder.command(Path("/recordings"))
        self.assertEqual(args[args.index("-segment_time") + 1], "60")
        self.assertEqual(args[args.index("-segment_atclocktime") + 1], "1")

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav"}, clear=True)
    def test_audio_uses_sample_clock_instead_of_http_arrival_time(self):
        args = recorder.command(Path("/recordings"))
        video_end = args.index("http://camera/video")
        audio_end = args.index("http://camera/audio.wav")
        self.assertIn("-use_wallclock_as_timestamps", args[:video_end])
        self.assertNotIn("-use_wallclock_as_timestamps", args[video_end + 1:audio_end])
        self.assertEqual(args[args.index("-af") + 1], "asetpts=N/SR/TB")

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav",
                             "SEGMENT_SECONDS": "0"}, clear=True)
    def test_reject_invalid_segment_length(self):
        with self.assertRaises(ValueError):
            recorder.command(Path("/recordings"))

    @patch.dict(os.environ, {"VIDEO_URL": "http://camera/video",
                             "AUDIO_URL": "http://camera/audio.wav"}, clear=True)
    def test_filename_prefix(self):
        for prefix in ("", "ipcam01", "camera-02_front"):
            with self.subTest(prefix=prefix), patch.dict(os.environ, {"FILENAME_PREFIX": prefix}):
                filename = Path(recorder.command(Path("/recordings"))[-1]).name
                expected = (prefix + "_" if prefix else "") + "%Y-%m-%d_%H-%M-%S_"
                self.assertTrue(filename.startswith(expected), filename)
        for prefix in ("../camera", "a/b", "a\\b", "%Y", "camera name"):
            with self.subTest(prefix=prefix), patch.dict(os.environ, {"FILENAME_PREFIX": prefix}):
                with self.assertRaises(ValueError):
                    recorder.command(Path("/recordings"))


if __name__ == "__main__":
    unittest.main()
