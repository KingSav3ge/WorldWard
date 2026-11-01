"""Real Store publication boundaries, using synthetic JSON records only.

These records exercise the file store, not Core initialization or a Creator
creation envelope. Injected faults are not process-crash/filesystem qualification.
No endpoint, ownership policy, reservation journal or provider is introduced.
"""
import copy
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Import the host first so its Engine-root bootstrap precedes assistance.
from server import Store
from assistance import sync_parent


class StoreWriteCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='worldward-store-characterization-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fixture(self, name, *, existing):
        store = Store(self.root / name)
        original = {'id': 'a' * 32, 'name': 'Synthetic storage boundary', 'revision': 0,
                    'state': {'clock': 0, 'synthetic_private_marker': 'old-only'}}
        if existing:
            store.write(original)
        path = store.path(original['id'])
        before = path.read_bytes() if path.exists() else None
        listing = store.listing()
        candidate = copy.deepcopy(original)
        candidate['revision'] = 1
        candidate['state'] = {'clock': 1, 'synthetic_private_marker': 'complete-new-record',
                              'nested': {'values': ['exact words <script>', 0, None]}}
        return store, path, before, listing, candidate

    def assert_prior_visibility(self, store, path, before, listing):
        if before is None:
            self.assertFalse(path.exists())
        else:
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(store.listing(), listing)

    def test_file_fsync_failure_preserves_visible_record_or_absence(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                store, path, before, listing, candidate = self.fixture(
                    'file-sync-' + str(existing), existing=existing)
                with patch('server.os.fsync', side_effect=OSError('injected file fsync failure')) as file_sync, \
                        patch.object(Path, 'replace', autospec=True) as replace, \
                        patch('server.sync_parent') as parent_sync:
                    with self.assertRaisesRegex(OSError, 'injected file fsync failure'):
                        store.write(candidate)
                    self.assertEqual(file_sync.call_count, 1)
                    replace.assert_not_called()
                    parent_sync.assert_not_called()
                # A temporary file may remain. It is not a published campaign.
                self.assert_prior_visibility(store, path, before, listing)

    def test_failed_replace_preserves_visible_record_or_absence(self):
        real_fsync = os.fsync
        for existing in (False, True):
            with self.subTest(existing=existing):
                store, path, before, listing, candidate = self.fixture(
                    'replace-' + str(existing), existing=existing)
                with patch('server.os.fsync', wraps=real_fsync) as file_sync, \
                        patch.object(Path, 'replace', autospec=True,
                                     side_effect=OSError('injected failure before replacement')) as replace, \
                        patch('server.sync_parent') as parent_sync:
                    with self.assertRaisesRegex(OSError, 'injected failure before replacement'):
                        store.write(candidate)
                    self.assertEqual(file_sync.call_count, 1)
                    replace.assert_called_once_with(path.with_suffix('.tmp'), path)
                    parent_sync.assert_not_called()
                self.assert_prior_visibility(store, path, before, listing)

    def test_parent_sync_failure_leaves_complete_replacement_visible(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                store, path, before, _, candidate = self.fixture(
                    'parent-sync-' + str(existing), existing=existing)
                expected = copy.deepcopy(candidate)
                with patch('server.sync_parent', side_effect=OSError('injected parent sync failure')) as parent_sync:
                    with self.assertRaisesRegex(OSError, 'injected parent sync failure'):
                        store.write(candidate)
                    parent_sync.assert_called_once_with(path)
                visible = path.read_bytes()
                self.assertEqual(json.loads(visible), expected)
                self.assertEqual(store.read(candidate['id']), expected)
                self.assertEqual(candidate, expected)
                self.assertNotEqual(visible, before)
                self.assertFalse(path.with_suffix('.tmp').exists())
                self.assertEqual(store.listing(), [
                    {key: candidate[key] for key in ('id', 'name', 'revision')}])
                # The raised exception is not evidence of rollback. No
                # Creator confirmation/status protocol exists in this test.

    @unittest.skipIf(os.name == 'nt',
                     'Windows sync_parent is a no-op; POSIX directory fsync is required for this case')
    def test_sync_only_confirmation_preserves_complete_visible_bytes(self):
        store, path, _, _, candidate = self.fixture('confirmation', existing=True)
        with patch('server.sync_parent', side_effect=OSError('unconfirmed publication')):
            with self.assertRaisesRegex(OSError, 'unconfirmed publication'):
                store.write(candidate)
        visible = path.read_bytes()
        self.assertEqual(json.loads(visible), candidate)

        # Neither read/retry path is allowed to serialize or replace the record.
        real_fsync = os.fsync
        directory_syncs = []

        def confirm_directory(descriptor):
            self.assertTrue(stat.S_ISDIR(os.fstat(descriptor).st_mode))
            directory_syncs.append(descriptor)
            return real_fsync(descriptor)

        with patch.object(Store, 'write', side_effect=AssertionError('confirmation must not rewrite')), \
                patch.object(Path, 'replace', side_effect=AssertionError('confirmation must not replace')):
            self.assertEqual(store.read(candidate['id']), candidate)
            self.assertEqual(path.read_bytes(), visible)
            # Repeated sync uncertainty also leaves the complete bytes intact.
            with patch('assistance.os.fsync', side_effect=OSError('still unconfirmed')):
                for _ in range(2):
                    with self.assertRaisesRegex(OSError, 'still unconfirmed'):
                        sync_parent(path)
                    self.assertEqual(path.read_bytes(), visible)
            with patch('assistance.os.fsync', side_effect=confirm_directory):
                for _ in range(2):
                    sync_parent(path)
                    self.assertEqual(store.read(candidate['id']), candidate)
                    self.assertEqual(path.read_bytes(), visible)
        self.assertEqual(len(directory_syncs), 2)


if __name__ == '__main__':
    unittest.main()
