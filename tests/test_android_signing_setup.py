"""Signing setup safety checks. No real GitHub settings or permanent keys are changed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'mobile/tools' / (name + '.py'))
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported
setup = module('phone_signing_setup')
verify = module('verify_signed_apk')


def keytool_works():
    if not shutil.which('keytool'):
        return False
    return subprocess.run(['keytool', '-help'], capture_output=True, check=False).returncode == 0


class PhoneSigningSetupTests(unittest.TestCase):
    def identity(self):
        return {'repository': setup.REPOSITORY, 'alias': 'scanner', 'sha256': 'a' * 64}
    def required(self):
        return {'ANDROID_KEYSTORE_BASE64', 'ANDROID_SIGNING_STORE_PASSWORD', 'ANDROID_SIGNING_KEY_ALIAS', 'ANDROID_SIGNING_KEY_PASSWORD'}
    def test_configuration_is_pinned_and_matching_retries_only_fill_missing_secrets(self):
        self.assertEqual(self.required(), setup.configuration_plan(set(), None, self.identity()))
        self.assertEqual(set(), setup.configuration_plan(self.required(), 'a' * 64, self.identity()))
        partial = self.required() - {'ANDROID_SIGNING_KEY_PASSWORD'}
        self.assertEqual({'ANDROID_SIGNING_KEY_PASSWORD'}, setup.configuration_plan(partial, 'a' * 64, self.identity()))
        for names, pin in [(self.required(), None), (set(), 'b' * 64)]:
            with self.assertRaises(ValueError): setup.configuration_plan(names, pin, self.identity())
    def test_raw_key_storage_rejects_git_checkouts_shared_storage_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').mkdir()
            with self.assertRaises(ValueError): setup.private_root(root / 'keys')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'target').mkdir(); (root / 'link').symlink_to(root / 'target')
            with self.assertRaises(ValueError): setup.private_root(root / 'link')
        with self.assertRaises(ValueError): setup.private_root('/storage/emulated/0/keys')
    def test_secret_file_creation_is_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'password'
            setup.write_private(path, b'PRIVATE_SENTINEL')
            self.assertEqual(0, path.stat().st_mode & 0o077)
            with self.assertRaises(FileExistsError): setup.write_private(path, b'changed')
            self.assertEqual(b'PRIVATE_SENTINEL', path.read_bytes())
    def test_subprocess_secrets_use_input_or_environment_not_arguments_or_errors(self):
        result = subprocess.CompletedProcess(['gh'], 1, b'PRIVATE_SENTINEL', b'PRIVATE_SENTINEL')
        with patch.object(setup.subprocess, 'run', return_value=result) as run:
            with self.assertRaises(RuntimeError) as error:
                setup.command(['gh', 'secret', 'set', 'NAME'], data=b'PRIVATE_SENTINEL')
        self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))
        self.assertNotIn('PRIVATE_SENTINEL', repr(run.call_args.args))
    def test_recovery_archive_is_fixed_and_never_extracted_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in setup.FILES: setup.write_private(root / name, name.encode())
            recovered = setup.read_archive(setup.archive(root))
            self.assertEqual({name: name.encode() for name in setup.FILES}, recovered)
        for names in [['../password.txt'], ['password.txt'] * 3]:
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode='w') as tar:
                for name in names:
                    member = tarfile.TarInfo(name); member.size = 1
                    tar.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(ValueError): setup.read_archive(output.getvalue())
    def test_existing_or_partial_identity_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'android-signing.p12').write_bytes(b'EXISTING_KEY')
            with patch.object(setup, 'command') as run:
                with self.assertRaises(ValueError): setup.create(root)
                run.assert_not_called()
            self.assertEqual(b'EXISTING_KEY', (root / 'android-signing.p12').read_bytes())
    def test_restore_refuses_to_overwrite_even_before_decryption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'password.txt').write_bytes(b'existing')
            with patch.object(setup, 'command') as run:
                with self.assertRaises(ValueError): setup.restore(root, Path('backup.age'))
                run.assert_not_called()
    def test_configure_preserves_existing_environment_and_writes_secrets_only_via_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); backup = root / 'backup.age'; backup.write_bytes(b'ENCRYPTED')
            (root / 'android-signing.p12').write_bytes(b'PRIVATE_KEY_SENTINEL')
            (root / 'backup-verified.json').write_text(json.dumps({'sha256': 'a'*64, 'backup_path': str(backup), 'backup_sha256': setup.hashlib.sha256(b'ENCRYPTED').hexdigest()}))
            existing = subprocess.CompletedProcess(['gh'], 0, b'{}', b'')
            with patch.object(setup, 'load_identity', return_value=('p'*48, self.identity())), patch('builtins.input', return_value='BACKED UP'), patch.object(setup.subprocess, 'run', return_value=existing), patch.object(setup, 'gh_json', side_effect=[{'secrets': []}, {'variables': []}, {}]) as api, patch.object(setup, 'command', return_value=b'') as run, contextlib.redirect_stdout(io.StringIO()):
                setup.configure(root)
            self.assertFalse(any(c.args[1:2] == ('PUT',) for c in api.call_args_list))
            secret_calls = [c for c in run.call_args_list if c.args[0][:3] == ['gh','secret','set']]
            self.assertEqual(4, len(secret_calls))
            self.assertTrue(all('--env' in c.args[0] and setup.ENVIRONMENT in c.args[0] for c in secret_calls))
            self.assertTrue(all('PRIVATE_KEY_SENTINEL' not in repr(c.args) and 'data' in c.kwargs for c in secret_calls))
    def test_build_never_updates_a_branch_without_complete_matching_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for pin in ['', 'b'*64]:
                with patch.object(setup, 'load_identity', return_value=('p'*48, self.identity())), patch.object(setup, 'gh_json', side_effect=[{'secrets': []}, {'variables': [{'name': setup.PIN, 'value': pin}]}]) as api:
                    with self.assertRaises(ValueError): setup.build(Path(tmp))
                    self.assertTrue(all(len(c.args) == 1 for c in api.call_args_list))
    def test_backup_is_decrypted_and_compared_before_marking_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in setup.FILES: setup.write_private(root / name, name.encode())
            backup = root / 'backup.age'; backup.write_bytes(b'ENCRYPTED_RECOVERY_FIXTURE')
            valid = setup.archive(root)
            with patch.object(setup, 'load_identity', return_value=('p'*48, self.identity())), patch.object(setup, 'command', return_value=valid), contextlib.redirect_stdout(io.StringIO()):
                setup.verify_backup(root, backup)
            self.assertEqual('a'*64, json.loads((root / 'backup-verified.json').read_text())['sha256'])
            (root / 'backup-verified.json').unlink()
            (root / 'password.txt').write_bytes(b'different')
            with patch.object(setup, 'load_identity', return_value=('p'*48, self.identity())), patch.object(setup, 'command', return_value=valid):
                with self.assertRaises(ValueError): setup.verify_backup(root, backup)
            self.assertFalse((root / 'backup-verified.json').exists())
    @unittest.skipUnless(keytool_works(), 'Java keytool is unavailable in this local runtime; CI runs this check')
    def test_real_disposable_key_can_be_loaded_and_is_not_regenerated_or_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = setup.private_root(Path(tmp) / 'keys')
            output = io.StringIO()
            with contextlib.redirect_stdout(output): setup.create(root)
            password, identity = setup.load_identity(root)
            original = (root / 'android-signing.p12').read_bytes()
            with contextlib.redirect_stdout(output): setup.create(root)
            self.assertEqual(original, (root / 'android-signing.p12').read_bytes())
            self.assertNotIn(password, output.getvalue())
            self.assertNotIn(setup.base64.b64encode(original).decode(), output.getvalue())
            self.assertEqual(64, len(identity['sha256']))


class SignedApkVerificationTests(unittest.TestCase):
    def candidate(self): return {'packageName': verify.PACKAGE, 'versionCode': 10, 'versionName': '0.9.0', 'signingSha256': 'a'*64}
    def test_accepts_same_identity_higher_version_and_rejects_wrong_package_key_or_downgrade(self):
        previous = dict(self.candidate(), versionCode=9)
        self.assertEqual(self.candidate(), verify.validate(self.candidate(), 'a'*64, previous))
        for candidate, pin, old in [(dict(self.candidate(), packageName='old.app'), 'a'*64, previous), (self.candidate(), 'b'*64, previous), (self.candidate(), '', previous), (self.candidate(), 'a'*64, self.candidate()), (self.candidate(), 'a'*64, dict(previous, signingSha256='b'*64))]:
            with self.assertRaises(ValueError): verify.validate(candidate, pin, old)
    def test_apk_signature_and_metadata_must_both_verify(self):
        signer = subprocess.CompletedProcess([], 0, 'Signer #1 certificate SHA-256 digest: ' + 'a'*64, '')
        badging = subprocess.CompletedProcess([], 0, "package: name='com.nsemomentum.paper.scanner' versionCode='10' versionName='0.9.0'", '')
        with patch.object(verify.subprocess, 'run', side_effect=[signer, badging]):
            self.assertEqual(self.candidate(), verify.inspect(Path('candidate.apk'), Path('/tools')))
        for first, second in [(subprocess.CompletedProcess([], 1, '', ''), badging), (signer, subprocess.CompletedProcess([], 0, badging.stdout + '\napplication-debuggable', '')), (signer, subprocess.CompletedProcess([], 0, 'invalid', ''))]:
            with patch.object(verify.subprocess, 'run', side_effect=[first, second]):
                with self.assertRaises(ValueError): verify.inspect(Path('candidate.apk'), Path('/tools'))


if __name__ == '__main__': unittest.main()
