import subprocess
from pathlib import Path
import tempfile
import unittest

from dream_rsi.repository_retrieval import queries, rank_file, retrieve


class RepositoryRetrievalTests(unittest.TestCase):
    def test_definition_outranks_mentions_and_trace_line_locates_body(self):
        query=queries('normalize_path() fails\n-> 120 return value.split("/")')
        definition=rank_file('paths.py','def normalize_path(value):\n    return value.split("/")\n',query)
        mention=rank_file('example.py','print(normalize_path("/tmp"))\n',query)
        self.assertGreater(definition['score'],mention['score'])
        self.assertIn('return value.split',definition['excerpt'])

    def test_scan_uses_tracked_source_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'paths.py').write_text('def normalize_path(value):\n    return value\n')
            (root/'untracked.py').write_text('def normalize_path(value):\n    return "untracked"\n')
            (root/'tests').mkdir()
            (root/'tests/test_paths.py').write_text('normalize_path("test")')
            (root/'escape.py').symlink_to(root/'untracked.py')
            subprocess.run(['git','-C',str(root),'add','paths.py','escape.py','tests'],check=True)
            result=retrieve(root,'normalize_path() should normalize a path')
            self.assertEqual([item['path'] for item in result['files']],['paths.py'])
            self.assertFalse(result['scan_truncated'])
            self.assertTrue(retrieve(root,'normalize_path()',max_bytes=1)['scan_truncated'])

    def test_no_code_evaluation_from_issue(self):
        query=queries('Fix parser.py; $(touch SECRET); eval("malicious")')
        self.assertIn('parser.py',query['filenames'])
        self.assertIsNone(rank_file('unrelated.py','VALUE = 1',query))
