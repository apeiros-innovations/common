import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / '.github/actions/select-checks/select.py'
spec = importlib.util.spec_from_file_location('selection', SOURCE)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Selection test')
        self.policy = {'version': 1, 'ignore_paths': ['README.md'],
                       'ignore_tools': ['aqua:betterleaks/betterleaks'],
                       'jobs': {'build': {'paths': ['src/**'], 'tools': ['go'], 'needs': ['versions']},
                                'docs': {'paths': ['docs/**'], 'tools': ['node']},
                                'versions': {'paths': [], 'tools': []}}}
        self.write('src/main.go', 'package main\n')
        self.write('README.md', 'readme\n')
        self.write('.mise/config.toml', '[tools]\ngo="1"\nnode="1"\n"aqua:betterleaks/betterleaks"="1"\n')
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture', '--allow-empty')
        return self.git('rev-parse', 'HEAD')

    def plan(self, event='push', **extra):
        head = self.git('rev-parse', 'HEAD')
        data = {'before': self.base, 'after': head, 'ref': 'refs/heads/main',
                'pull_request': {'base': {'sha': self.base}, 'head': {'sha': head}},
                'merge_group': {'base_sha': self.base, 'head_sha': head}}
        data.update(extra)
        return selection.select(self.root, self.policy, event, data)[0]

    def test_readme_skips(self):
        self.write('README.md', 'new'); self.commit()
        self.assertEqual(self.plan(), dict.fromkeys(self.policy['jobs'], False))

    def test_betterleaks_only_skips(self):
        p = self.root / '.mise/config.toml'
        p.write_text(p.read_text().replace('betterleaks"="1"', 'betterleaks"="2"')); self.commit()
        self.assertFalse(any(self.plan().values()))

    def test_relevant_tool_selects_dependency(self):
        p = self.root / '.mise/config.toml'
        p.write_text(p.read_text().replace('go="1"', 'go="2"')); self.commit()
        self.assertEqual(self.plan(), {'build': True, 'docs': False, 'versions': True})

    def test_shared_settings_select_all(self):
        p = self.root / '.mise/config.toml'
        p.write_text(p.read_text() + '\n[env]\nFLAG="1"\n'); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_unknown_tool_selects_all(self):
        p = self.root / '.mise/config.toml'
        p.write_text(p.read_text() + 'newtool="1"\n'); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_lock_checksum_change(self):
        self.write('.mise/mise.lock', '[[tools.go]]\nversion="1"\nchecksum="old"\n')
        self.base = self.commit()
        self.write('.mise/mise.lock', '[[tools.go]]\nversion="1"\nchecksum="new"\n'); self.commit()
        self.assertEqual(self.plan(), {'build': True, 'docs': False, 'versions': True})

    def test_invalid_toml_or_deleted_config_selects_all(self):
        self.write('.mise/config.toml', '[invalid'); self.commit()
        self.assertTrue(all(self.plan().values()))
        (self.root / '.mise/config.toml').unlink(); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_unknown_path_selects_all(self):
        self.write('new-feature/file', 'new'); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_policy_edit_selects_all(self):
        self.write('.github/ci-impact.json', json.dumps(self.policy)); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_deletion_and_rename_both_sides(self):
        self.git('mv', 'src/main.go', 'README.md.new'); self.commit()
        self.policy['ignore_paths'].append('README.md.new')
        self.assertTrue(self.plan()['build'])

    def test_pr_keeps_earlier_commit_and_ignores_unrelated_base(self):
        self.write('src/main.go', 'changed'); self.commit()
        self.write('README.md', 'new'); self.commit()
        head = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-qb', 'base-advance', self.base)
        self.write('docs/new.md', 'base only'); newbase = self.commit()
        result = self.plan('pull_request', pull_request={'base': {'sha': newbase}, 'head': {'sha': head}})
        self.assertEqual(result, {'build': True, 'docs': False, 'versions': True})

    def test_merge_queue_and_multicommit_push(self):
        self.write('src/main.go', 'changed'); self.commit()
        self.write('README.md', 'new'); self.commit()
        self.assertTrue(self.plan('merge_group')['build'])
        self.assertTrue(self.plan()['build'])

    def test_full_events_and_missing_history(self):
        for event in ('workflow_dispatch', 'schedule'):
            self.assertTrue(all(self.plan(event).values()))
        self.assertTrue(all(self.plan(before='0'*40).values()))
        self.assertTrue(all(self.plan(before='f'*40).values()))
        self.assertTrue(all(self.plan(created=True).values()))
        self.assertTrue(all(self.plan(ref='refs/tags/v1').values()))

    def test_privileged_events_rejected(self):
        for event in ('pull_request_target', 'workflow_run'):
            with self.assertRaises(ValueError): self.plan(event)

    def test_spaces_newlines_and_exclusion(self):
        self.policy['jobs']['build']['paths'] = ['src/**', ':(glob,exclude)docs/**']
        self.write('src/a file\nwith newline', 'x'); self.commit()
        self.assertTrue(self.plan()['build'])

    def test_ignored_path_does_not_override_job_dependency(self):
        self.policy['jobs']['docs']['paths'].append('README.md')
        self.write('README.md', 'new'); self.commit()
        self.assertTrue(self.plan()['docs'])

    def test_raw_manifest_validation(self):
        self.policy["jobs"]["docs"].update(raw_mise=True, paths=[".mise/config.toml"])
        p = self.root / ".mise/config.toml"
        p.write_text(p.read_text() + "\n# formatting\n"); self.commit()
        self.assertEqual(self.plan(), {"build": False, "docs": True, "versions": False})

    def test_related_workflow_policy_edit_selects_all(self):
        self.write(".github/ci-impact/catalog.json", "{}"); self.commit()
        self.assertTrue(all(self.plan().values()))

    def test_invalid_policy_fails(self):
        self.policy['jobs']['build']['needs'] = ['typo']
        with self.assertRaises(ValueError): self.plan()

if __name__ == '__main__':
    unittest.main()
