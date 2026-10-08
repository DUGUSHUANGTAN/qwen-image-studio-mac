"""Editing must preserve boolean causal masks and reject unsafe custom settings."""
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/web'))
import server

BASE = dict(prompt='Change the shirt to blue', steps=40, seed=42, ratio=None)
MODELS = dict(unet='qwen_image_2.1_int8_convrot.safetensors', clip='qwen3vl_8b_int8_convrot.safetensors', vae='qwen_image_2.1_vae_bf16.safetensors')

class EditQualityTest(unittest.TestCase):
    def test_mps_edit_requires_cpu_vae(self):
        for flags, expected in (([], False), (['--cpu-vae'], True)):
            with patch.object(server, '_http_json', return_value={'devices': [{'type': 'mps'}], 'system': {'argv': flags}}):
                self.assertEqual(server.ComfyBackend._safe_for_edit('http://test'), expected)
        with patch.object(server, '_http_json', return_value={'devices': [{'type': 'cuda'}], 'system': {'argv': []}}):
            self.assertTrue(server.ComfyBackend._safe_for_edit('http://test'))

    def test_unsafe_explicit_url_is_rejected_for_edit(self):
        backend = server.ComfyBackend('http://test')
        with patch.object(server, 'comfy_alive', return_value=True), patch.object(backend, '_safe_for_edit', return_value=False):
            with self.assertRaisesRegex(ValueError, '--cpu-vae'):
                backend.resolve(editing=True)
            self.assertEqual(backend.resolve(), 'http://test')

    def test_mac_automatic_start_adds_cpu_vae(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'main.py').touch()
            backend = server.ComfyBackend(folder)
            with patch.object(server.sys, 'platform', 'darwin'), \
                 patch.object(server, 'comfy_alive', side_effect=[False, False, False, True]), \
                 patch.object(server, '_port_busy', return_value=False), \
                 patch.object(backend, '_find_python', return_value=Path('/python')), \
                 patch.object(server.subprocess, 'Popen') as start:
                self.assertEqual(backend.resolve(editing=True), 'http://127.0.0.1:8188')
                self.assertIn('--cpu-vae', start.call_args.args[0])

    def test_cached_unsafe_server_is_rechecked_before_edit(self):
        backend = server.ComfyBackend('http://test')
        backend.base = 'http://test'
        with patch.object(server, 'comfy_alive', return_value=True), \
             patch.object(backend, '_sees_models', return_value=True), \
             patch.object(backend, '_safe_for_edit', return_value=False):
            with self.assertRaisesRegex(ValueError, '--cpu-vae'):
                backend.resolve(editing=True)

    def test_edit_guard_rejects_low_steps_and_large_canvas(self):
        for settings in ({**BASE, 'steps': 8}, {**BASE, 'width': 2048, 'height': 2048}, {**BASE, 'width': 1024}):
            with self.assertRaises(ValueError):
                server.validate_edit_settings(settings)

    def test_official_template_and_default_parameters_are_accepted(self):
        for settings in (BASE, {**BASE, 'steps': 25}, {**BASE, 'width': 1024, 'height': 1024}):
            server.validate_edit_settings(settings)

    def test_invalid_edit_is_rejected_before_queue_or_comfy_start(self):
        runner = object.__new__(server.Runner)
        runner.state = Mock()
        runner.state.session_name.return_value = 'test'
        runner.state.inputs.return_value = [{'name': 'reference'}]
        # No queue or backend exists: reaching either would make this test fail.
        with self.assertRaisesRegex(ValueError, 'at least 25 steps'):
            runner.submit({**BASE, 'steps': 8})

if __name__ == '__main__':
    unittest.main()
