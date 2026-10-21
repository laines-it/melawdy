import copy
import json
from pathlib import Path
import tempfile
import unittest

from core import compare_infos, load_info
from run import generate_examples, main


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        generate_examples(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def path(self, name):
        return self.directory / f"{name}.json"

    def test_identical_melody_ranks_above_different_pitch_classes(self):
        result = compare_infos(self.path("query"), [self.path("different"), self.path("same_melody")])
        self.assertEqual(result["status"], "ok")
        same, different = result["matches"]
        self.assertEqual(same["title"], "same_melody")
        self.assertGreater(same["score"], different["score"])
        self.assertGreater(same["score"], 0.8)
        # The original metric still rewards identical onset rhythm when pitch differs.
        self.assertLess(different["score"], 0.2)
        for match in result["matches"]:
            for pair in match["top_segments"]:
                self.assertLessEqual(pair["query_end"], 16.0)
                self.assertLessEqual(pair["reference_end"], 16.0)

    def test_octave_invariance_and_batch_boundaries(self):
        paths = [self.path("same_melody"), self.path("octave_up")]
        one = compare_infos(self.path("query"), paths, batch_size=1)
        four = compare_infos(self.path("query"), paths, batch_size=4)
        self.assertEqual([x["score"] for x in one["matches"]], [x["score"] for x in four["matches"]])
        self.assertEqual(one["matches"][0]["score"], one["matches"][1]["score"])

    def test_empty_vocals_are_an_explicit_result(self):
        result = compare_infos(self.path("no_notes"), [self.path("same_melody")])
        self.assertEqual(result["status"], "no_query_segments")
        self.assertEqual(result["matches"], [])
        result = compare_infos(self.path("query"), [self.path("no_notes")])
        self.assertEqual(result["status"], "no_reference_segments")
        self.assertEqual(len(result["skipped"]), 1)

    def test_invalid_timing_and_meter_are_rejected(self):
        original = json.loads(self.path("query").read_text())
        for change in ({"rhythm": 3}, {"bpm": 0}, {"bpm": float("nan")}, {"beat_times": [1, 0]}):
            data = copy.deepcopy(original)
            data.update(change)
            path = self.directory / "invalid.json"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_info(path)

    def test_cli_writes_json_and_escaped_html(self):
        data = json.loads(self.path("same_melody").read_text())
        data["title"] = '<script>alert("test")</script>'
        path = self.directory / "named.json"
        path.write_text(json.dumps(data))
        output = self.directory / "output" / "result.json"
        code = main(["compare-json", str(self.path("query")), "--reference", str(path), "--output", str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text())["matches"][0]["title"], data["title"])
        report = output.with_suffix(".html").read_text()
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)

    def test_missing_file_and_output_overwrite_are_rejected(self):
        missing = main(["compare-json", str(self.path("missing")), "--reference", str(self.path("query"))])
        self.assertEqual(missing, 2)
        original = self.path("query").read_bytes()
        code = main(["compare-json", str(self.path("query")), "--reference", str(self.path("same_melody")),
                     "--output", str(self.path("query"))])
        self.assertEqual(code, 2)
        self.assertEqual(self.path("query").read_bytes(), original)

    def test_examples_do_not_replace_user_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "query.json").write_text("user content")
            generate_examples(directory)
            self.assertEqual((directory / "query.json").read_text(), "user content")


if __name__ == "__main__":
    unittest.main()
