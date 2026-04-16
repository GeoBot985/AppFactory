import unittest
from Demo10.editing.anchor_resolver import AnchorResolver
from Demo10.editing.models import AnchorType, MatchMode, AnchorStatus

class TestAnchorResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = AnchorResolver()
        self.sample_python = [
            "import os\n",
            "from pathlib import Path\n",
            "\n",
            "@decorator\n",
            "def foo(x):\n",
            "    return x + 1\n",
            "\n",
            "class Bar:\n",
            "    def method(self):\n",
            "        pass\n",
            "\n",
            "# BEGIN: region1\n",
            "x = 10\n",
            "# END: region1\n"
        ]

    def test_resolve_function(self):
        res = self.resolver.resolve(self.sample_python, AnchorType.FUNCTION, "foo")
        self.assertEqual(res.status, AnchorStatus.OK)
        self.assertEqual(res.selected_match.start_line, 3) # Including decorator
        self.assertEqual(res.selected_match.end_line, 5)

    def test_resolve_class(self):
        res = self.resolver.resolve(self.sample_python, AnchorType.CLASS, "Bar")
        self.assertEqual(res.status, AnchorStatus.OK)
        self.assertEqual(res.selected_match.start_line, 7)
        self.assertEqual(res.selected_match.end_line, 9)

    def test_resolve_import(self):
        res = self.resolver.resolve(self.sample_python, AnchorType.IMPORT, "import os")
        self.assertEqual(res.status, AnchorStatus.OK)
        self.assertEqual(res.selected_match.start_line, 0)

    def test_resolve_region(self):
        res = self.resolver.resolve(self.sample_python, AnchorType.REGION_MARKER, "region1")
        self.assertEqual(res.status, AnchorStatus.OK)
        self.assertEqual(res.selected_match.start_line, 11)
        self.assertEqual(res.selected_match.end_line, 13)

    def test_not_found(self):
        res = self.resolver.resolve(self.sample_python, AnchorType.FUNCTION, "missing")
        self.assertEqual(res.status, AnchorStatus.NOT_FOUND)

if __name__ == "__main__":
    unittest.main()
