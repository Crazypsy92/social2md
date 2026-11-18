import unittest

from cloud_runner import _make_parser


class CloudBatchDefaultsTests(unittest.TestCase):
    def test_default_batch_size_is_30(self):
        args = _make_parser().parse_args(["-u", "https://www.douyin.com/user/test"])
        self.assertEqual(args.batch_size, 30)
        self.assertEqual(args.max_items, 0)

    def test_batch_size_remains_configurable(self):
        args = _make_parser().parse_args(["-u", "https://www.douyin.com/user/test", "--batch-size", "12"])
        self.assertEqual(args.batch_size, 12)


if __name__ == "__main__":
    unittest.main()
