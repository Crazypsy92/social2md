import unittest

from social2md_app.cli import _make_parser


class UnifiedPipelineTests(unittest.TestCase):
    def test_exactly_one_source_is_required(self):
        parser = _make_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_multiple_sources_are_rejected(self):
        parser = _make_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["-u", "https://www.douyin.com/user/test", "--input-dir", "/tmp/videos"])

    def test_keep_source_is_opt_in(self):
        args = _make_parser().parse_args(["--input-dir", "/tmp/videos"])
        self.assertFalse(args.keep_source)


if __name__ == "__main__":
    unittest.main()
