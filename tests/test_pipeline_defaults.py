import unittest

from social2md_app.cli import _make_parser


class PipelineDefaultsTests(unittest.TestCase):
    def test_default_batch_size_is_30(self):
        args = _make_parser().parse_args(["-u", "https://www.douyin.com/user/test"])
        self.assertEqual(args.batch_size, 30)
        self.assertEqual(args.max_items, 0)

    def test_input_directory_uses_same_pipeline(self):
        args = _make_parser().parse_args(["--input-dir", "/tmp/videos"])
        self.assertEqual(str(args.input_dir), "/tmp/videos")

    def test_document_directory_uses_same_pipeline(self):
        args = _make_parser().parse_args(["--document-dir", "/tmp/documents"])
        self.assertEqual(str(args.document_dir), "/tmp/documents")


if __name__ == "__main__":
    unittest.main()
