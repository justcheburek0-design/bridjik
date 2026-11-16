import unittest
from utils.history_context import context_messages


class HistoryContextTests(unittest.TestCase):
    def test_boundary_and_immutability(self):
        rows = [(i, 'author', False, 'x'*4000, b'image', 'image/png', None, {}) for i in range(200)]
        result = context_messages(rows)
        self.assertEqual(len(result), 200)
        self.assertTrue(result[149][3].endswith('[сокращено]'))
        self.assertLess(len(result[149][3]), 520)
        self.assertIsNone(result[149][4])
        self.assertEqual(result[150], rows[150])
        self.assertEqual(len(rows[149][3]), 4000)
        self.assertEqual(rows[149][4], b'image')

    def test_limits_and_short_messages(self):
        rows = [(i, 'a', False, 'short', None, None, None, {}) for i in range(250)]
        result = context_messages(rows)
        self.assertEqual(len(result), 200)
        self.assertEqual(result[0][0], 50)
        self.assertEqual(result[0][3], 'short')
        self.assertEqual(context_messages(rows[:50]), rows[:50])
        self.assertEqual(context_messages([]), [])
