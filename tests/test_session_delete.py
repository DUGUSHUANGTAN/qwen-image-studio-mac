"""Deleting an instance removes only its images, preserving shared files.

Images live once, in Input/ and Output/ — those folders are the storage, not
a cache of an internal copy. A reference taken from the gallery shares the
take's file rather than duplicating it, so deletion has to go by path: an
asset_id still held by another session keeps the file on disk.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_server', ROOT / 'app/web/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DeleteSessionTest(unittest.TestCase):
    def test_removes_owned_takes_and_inputs_but_keeps_other_session_files(self):
        with tempfile.TemporaryDirectory() as data:
            state = server.State({'comfyui': ''}, Path(data))
            first = state.activate('FIRST')
            first_id = state.session(first['name'])['id']
            second = state.activate('SECOND')
            second_id = state.session(second['name'])['id']

            # one file per asset, in the folder that owns it.
            # thumbs are named by asset_id, which is what _drop_thumbs looks up
            assets = ('aaaaaaaaaaaa', 'bbbbbbbbbbbb', 'cccccccccccc')
            owned_only, shared, other_only = (state.output_dir / f'{a}.png' for a in assets)
            for path, asset in zip((owned_only, shared, other_only), assets):
                path.write_bytes(b'image')
                (state.thumbs_dir / f'{asset}.png').write_bytes(b'thumb')

            # SECOND holds the shared take as a reference — no copy, same file
            state._data['sessions'][second_id]['inputs']['shared'] = {
                'asset_id': 'bbbbbbbbbbbb', 'original_name': 'bbbbbbbbbbbb.png',
                'file': 'Output/bbbbbbbbbbbb.png', 'added': server.now_iso(),
            }
            state._data['gallery'] = {
                'one': {'id': 'one', 'session_id': first_id, 'asset_id': 'aaaaaaaaaaaa',
                        'params': {'name': 'aaaaaaaaaaaa.png'}},
                'two': {'id': 'two', 'session_id': first_id, 'asset_id': 'bbbbbbbbbbbb',
                        'params': {'name': 'bbbbbbbbbbbb.png'}},
                'three': {'id': 'three', 'session_id': second_id, 'asset_id': 'cccccccccccc',
                          'params': {'name': 'cccccccccccc.png'}},
            }
            state._save()

            state.delete_session('FIRST')

            # FIRST's gallery entries are gone; SECOND's stay
            self.assertEqual(set(state._data['gallery']), {'three'})
            # the take only FIRST referenced is deleted, file and thumb
            self.assertFalse(owned_only.exists())
            self.assertFalse((state.thumbs_dir / 'aaaaaaaaaaaa.png').exists())
            # the shared file survives — SECOND still points at it
            self.assertTrue(shared.exists())
            self.assertTrue((state.thumbs_dir / 'bbbbbbbbbbbb.png').exists())
            self.assertTrue(other_only.exists())


if __name__ == '__main__':
    unittest.main()