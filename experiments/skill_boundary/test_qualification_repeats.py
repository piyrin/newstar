import hashlib
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock

from runner import BASE, read, save
from qualification_repeats import freeze_campaign, make_jobs, run_campaign


class RepeatedQualification(unittest.TestCase):
    def fixture(self):
        root = BASE / 'offline-tests' / str(uuid.uuid4())
        root.mkdir(parents=True)
        source = root / 'original.md'
        source.write_text('Rewrite supplied prose without adding facts.', encoding='utf-8')
        row = {'tool_name': 'rewrite', 'name': 'rewrite', 'path': str(source),
               'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'normalized_sha256': 'unique-source', 'source_url': 'offline-fixture'}
        case = {'eligible': True, 'request': 'Rewrite this sentence.',
                'facts': {'text': 'The input.'}, 'checks': ['a', 'b', 'c'],
                'scope': 'text draft', 'boundary': 'Do not invent facts.',
                'source_quote': 'Rewrite supplied prose without adding facts.'}
        return root, row, case

    def test_three_distinct_draws_and_one_separate_same_seed_reproduction(self):
        jobs = make_jobs(['a', 'b'], [101, 102, 103])
        self.assertEqual(len(jobs), 8)
        self.assertEqual(len({j['id'] for j in jobs}), 8)
        for name in ['a', 'b']:
            selected = [j for j in jobs if j['tool_name'] == name]
            self.assertEqual([j['seed'] for j in selected], [101, 102, 103, 101])
            self.assertEqual([j['kind'] for j in selected],
                             ['independent_seed'] * 3 + ['same_seed_reproduction'])
            self.assertEqual(selected[-1]['reproduces'], selected[0]['id'])
        with self.assertRaises(ValueError):
            make_jobs(['a'], [101, 101, 103])

    def test_campaign_freezes_source_bytes_not_live_original_path(self):
        root, row, case = self.fixture()
        campaign = root / 'campaign'
        freeze_campaign(campaign, [row], {'rewrite': case}, [101, 102, 103])
        frozen = read(campaign / 'registry.json')[0]
        Path(row['path']).write_text('changed after freeze', encoding='utf-8')
        self.assertEqual((campaign / frozen['path']).read_text(encoding='utf-8'),
                         'Rewrite supplied prose without adding facts.')
        with self.assertRaises(FileExistsError):
            freeze_campaign(campaign, [row], {'rewrite': case}, [101, 102, 103])

    def test_source_hash_mismatch_rejected_before_inference(self):
        root, row, case = self.fixture()
        row['sha256'] = 'wrong'
        with self.assertRaises(ValueError):
            freeze_campaign(root / 'campaign', [row], {'rewrite': case}, [101, 102, 103])

    def test_partial_attempt_is_preserved_and_never_silently_retried(self):
        root, row, case = self.fixture()
        campaign = root / 'campaign'
        freeze_campaign(campaign, [row], {'rewrite': case}, [101, 102, 103])
        first = read(campaign / 'jobs.json')[0]
        (campaign / 'trials' / first['id']).mkdir(parents=True)
        api = Mock()
        with self.assertRaisesRegex(RuntimeError, 'partial attempt preserved'):
            run_campaign(campaign, api_factory=api)
        api.assert_not_called()

    def test_stop_before_first_job_preserves_zero_completed_denominator(self):
        root, row, case = self.fixture()
        campaign = root / 'campaign'
        freeze_campaign(campaign, [row], {'rewrite': case}, [101, 102, 103])
        (campaign / 'STOP_AFTER_CURRENT').touch()
        api = Mock()
        result = run_campaign(campaign, api_factory=api)
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['planned'], 4)
        self.assertEqual(result['status'], 'stopped_after_current')
        api.assert_not_called()

    def test_failed_trials_remain_in_denominator_and_reproduction_is_not_new_seed(self):
        root, row, case = self.fixture()
        campaign = root / 'campaign'
        freeze_campaign(campaign, [row], {'rewrite': case}, [101, 102, 103])
        seeds = []
        def factory(**kwargs):
            seeds.append(kwargs['seed'])
            return Mock(model='offline-test-double')
        outcomes = iter([False, True, False, True])
        def qualifier(api, row, folder, **kwargs):
            folder.mkdir(parents=True)
            result = {'passed': next(outcomes), 'tool_name': row['tool_name'],
                      'source_sha256': row['sha256']}
            save(folder / 'summary.json', result)
            return result
        result = run_campaign(campaign, api_factory=factory, qualifier=qualifier)
        self.assertEqual(seeds, [101, 102, 103, 101])
        self.assertEqual((result['completed'], result['planned']), (4, 4))
        self.assertEqual(result['automatic_passed'], 2)
        self.assertEqual(result['planned_independent_trials'], 3)
        self.assertEqual(result['planned_reproductions'], 1)
        self.assertNotIn('stable', result)


if __name__ == '__main__':
    unittest.main()
