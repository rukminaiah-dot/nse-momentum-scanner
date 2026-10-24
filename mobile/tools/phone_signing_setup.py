#!/usr/bin/env python3
"""One-time owner-run signing setup. Secrets never appear in arguments or output.
Run inside Termux private storage; this script is never run by a build to mint a release key.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import tarfile
import tempfile

REPOSITORY = "rukminaiah-dot/nse-momentum-scanner"
ENVIRONMENT = "android-experimental-signing"
BRANCH = "experiment/android-paper-scanner"
PIN = "ANDROID_SIGNING_CERT_SHA256"
FILES = {"android-signing.p12", "password.txt", "identity.json"}


def command(args, *, data=None, env=None, interactive=False):
    result = subprocess.run(args, input=data, env=env, stdout=None if interactive else subprocess.PIPE,
                            stderr=None if interactive else subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} could not complete this step. Private output was suppressed.")
    return result.stdout or b""


def private_root(root):
    root = Path(root).expanduser().absolute()
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("Private signing storage cannot use symbolic links.")
    if str(root).startswith(("/storage/", "/sdcard/")):
        raise ValueError("Keep raw signing files inside Termux private storage.")
    if any((p / ".git").exists() for p in [root, *root.parents]):
        raise ValueError("Signing storage must be outside every Git checkout.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def cert_digest(keystore, password):
    env = dict(os.environ, NSE_SIGNING_PASSWORD=password)
    der = command(["keytool", "-exportcert", "-keystore", str(keystore), "-alias", "scanner",
                   "-storepass:env", "NSE_SIGNING_PASSWORD"], env=env)
    return hashlib.sha256(der).hexdigest()


def load_identity(root):
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("Signing files are missing or their permissions are too broad.")
    password = (root / "password.txt").read_text().strip()
    identity = json.loads((root / "identity.json").read_text())
    if len(password) < 32 or identity.get("repository") != REPOSITORY or identity.get("alias") != "scanner":
        raise ValueError("Invalid signing identity.")
    if cert_digest(root / "android-signing.p12", password) != identity.get("sha256"):
        raise ValueError("Signing certificate changed; refusing to continue.")
    return password, identity


def create(root):
    if any((root / name).exists() for name in FILES):
        _, identity = load_identity(root)
        print("Existing signing identity retained. Public certificate SHA256:", identity["sha256"])
        return
    password = secrets.token_urlsafe(36)
    with tempfile.TemporaryDirectory(prefix="key-", dir=root) as temporary:
        key = Path(temporary) / "key.p12"
        env = dict(os.environ, NSE_SIGNING_PASSWORD=password)
        command(["keytool", "-genkeypair", "-keystore", str(key), "-storetype", "PKCS12", "-alias", "scanner",
                 "-keyalg", "RSA", "-keysize", "4096", "-validity", "10000",
                 "-dname", "CN=NSE Momentum Experimental, O=Private Paper Scanner, C=IN",
                 "-storepass:env", "NSE_SIGNING_PASSWORD", "-keypass:env", "NSE_SIGNING_PASSWORD"], env=env)
        identity = {"repository": REPOSITORY, "alias": "scanner", "sha256": cert_digest(key, password)}
        write_private(root / "android-signing.p12", key.read_bytes())
        write_private(root / "password.txt", password.encode())
        write_private(root / "identity.json", json.dumps(identity).encode())
    print("Private signing key created on this device. Public certificate SHA256:", identity["sha256"])
    print("Next: create and verify the encrypted recovery backup before configuring GitHub.")


def archive(root):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for name in sorted(FILES):
            data = (root / name).read_bytes()
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return out.getvalue()


def read_archive(data):
    if len(data) > 1_000_000:
        raise ValueError("Recovery archive is too large.")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        members = tar.getmembers()
        if len(members) != 3 or {m.name for m in members} != FILES or any(not m.isfile() for m in members):
            raise ValueError("Invalid recovery archive entries.")
        if any(m.size > 100_000 for m in members):
            raise ValueError("Recovery archive entry too large.")
        return {m.name: tar.extractfile(m).read() for m in members}


def backup(root):
    _, identity = load_identity(root)
    destination = root / "android-signing-backup.age"
    if destination.exists():
        raise ValueError("Backup already exists. It will not be overwritten; use verify-backup.")
    print("Choose a recovery passphrase in the age prompt. Keep it in your password manager, outside chat.")
    command(["age", "--passphrase", "--output", str(destination)], data=archive(root), interactive=True)
    destination.chmod(0o600)
    verify_backup(root, destination)


def verify_backup(root, source):
    _, identity = load_identity(root)
    recovered = read_archive(command(["age", "--decrypt", str(source)]))
    if any(recovered[name] != (root / name).read_bytes() for name in FILES):
        raise ValueError("Recovery verification failed. GitHub signing was not configured.")
    marker = {"sha256": identity["sha256"], "backup_path": str(Path(source).absolute()),
              "backup_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest()}
    marker_path = root / "backup-verified.json"
    if marker_path.is_symlink():
        raise ValueError("Invalid backup marker.")
    marker_path.write_text(json.dumps(marker))
    marker_path.chmod(0o600)
    print("Encrypted recovery backup successfully decrypted and compared with the signing identity.")


def restore(root, source):
    if any((root / name).exists() for name in FILES):
        raise ValueError("An identity already exists. Restore will never overwrite it.")
    recovered = read_archive(command(["age", "--decrypt", str(source)]))
    # Verify in a private temporary directory before retaining any recovered identity.
    with tempfile.TemporaryDirectory(prefix="restore-", dir=root) as directory:
        temporary = Path(directory)
        for name, data in recovered.items():
            write_private(temporary / name, data)
        load_identity(temporary)
        for name, data in recovered.items():
            write_private(root / name, data)
    verify_backup(root, source)
    print("Existing signing identity restored. No replacement key was generated.")


def gh_json(path, method="GET", payload=None):
    args = ["gh", "api", "--hostname", "github.com", "--method", method, path]
    if payload is not None:
        args += ["--input", "-"]
    output = command(args, data=json.dumps(payload).encode() if payload is not None else None)
    return json.loads(output or b"{}")


def configuration_plan(secret_names, remote_pin, identity):
    required = {"ANDROID_KEYSTORE_BASE64", "ANDROID_SIGNING_STORE_PASSWORD", "ANDROID_SIGNING_KEY_ALIAS", "ANDROID_SIGNING_KEY_PASSWORD"}
    if remote_pin and remote_pin.lower() != identity["sha256"]:
        raise ValueError("GitHub already pins a different signing key. Nothing will be overwritten.")
    if not remote_pin and required.intersection(secret_names):
        raise ValueError("Existing signing secrets have no identity pin. Review them before making changes.")
    return required - set(secret_names)


def configure(root):
    password, identity = load_identity(root)
    marker = json.loads((root / "backup-verified.json").read_text())
    if marker.get("sha256") != identity["sha256"] or hashlib.sha256(Path(marker["backup_path"]).read_bytes()).hexdigest() != marker["backup_sha256"]:
        raise ValueError("Create and verify your encrypted backup first.")
    if input("Copy the encrypted .age backup outside Termux and retain its passphrase separately. Type BACKED UP when done: ") != "BACKED UP":
        raise ValueError("Setup paused before changing GitHub.")
    command(["gh", "auth", "status", "--hostname", "github.com"])
    endpoint = f"repos/{REPOSITORY}/environments/{ENVIRONMENT}"
    # Creation/update affects only this dedicated experimental environment.
    existing = subprocess.run(["gh", "api", "--hostname", "github.com", endpoint], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if existing.returncode:
        if b"HTTP 404" not in existing.stderr:
            raise RuntimeError("Cannot inspect the Android signing environment. Existing settings were retained.")
        gh_json(endpoint, "PUT", {})
    names = {s["name"] for s in gh_json(endpoint + "/secrets?per_page=100").get("secrets", [])}
    variables = {v["name"]: v["value"] for v in gh_json(endpoint + "/variables?per_page=100").get("variables", [])}
    missing = configuration_plan(names, variables.get(PIN), identity)
    if not variables.get(PIN):
        gh_json(endpoint + "/variables", "POST", {"name": PIN, "value": identity["sha256"]})
    values = {"ANDROID_KEYSTORE_BASE64": base64.b64encode((root / "android-signing.p12").read_bytes()),
              "ANDROID_SIGNING_STORE_PASSWORD": password.encode(), "ANDROID_SIGNING_KEY_ALIAS": b"scanner",
              "ANDROID_SIGNING_KEY_PASSWORD": password.encode()}
    for name in sorted(missing):
        command(["gh", "secret", "set", name, "--repo", REPOSITORY, "--env", ENVIRONMENT], data=values[name])
    print("Android-only signing environment configured. Existing matching secrets were retained.")
    print("No release was published. Next: run the build command for the experimental signed candidate.")


def build(root):
    _, identity = load_identity(root)
    environment = f"repos/{REPOSITORY}/environments/{ENVIRONMENT}"
    names = {s["name"] for s in gh_json(environment + "/secrets?per_page=100").get("secrets", [])}
    variables = {v["name"]: v["value"] for v in gh_json(environment + "/variables?per_page=100").get("variables", [])}
    if configuration_plan(names, variables.get(PIN), identity) or not variables.get(PIN):
        raise ValueError("Complete signing configuration before requesting a build.")
    # An empty experimental commit triggers its push workflow without changing app or production code.
    endpoint = f"repos/{REPOSITORY}"
    ref = gh_json(endpoint + "/git/ref/heads/" + BRANCH)
    head = ref["object"]["sha"]
    commit = gh_json(endpoint + "/git/commits/" + head)
    created = gh_json(endpoint + "/git/commits", "POST", {"message": "Build private Android signed candidate", "tree": commit["tree"]["sha"], "parents": [head]})
    gh_json(endpoint + "/git/refs/heads/" + BRANCH, "PATCH", {"sha": created["sha"], "force": False})
    print("Experimental signed candidate requested. No merge, deployment or release publication.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "backup", "verify-backup", "restore", "configure", "build"])
    parser.add_argument("--private-dir", type=Path, default=Path.home().resolve() / ".local/share/nse-paper-signing")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        root = private_root(args.private_dir)
        if args.action == "build":
            build(root)
            return
        if args.action == "create": create(root)
        elif args.action == "backup": backup(root)
        elif args.action == "verify-backup": verify_backup(root, args.backup or root / "android-signing-backup.age")
        elif args.action == "restore":
            if not args.backup: raise ValueError("Specify the encrypted recovery file with --backup.")
            restore(root, args.backup)
        else: configure(root)
    except (RuntimeError, ValueError, OSError, KeyError, tarfile.TarError, json.JSONDecodeError) as error:
        # Never emit raw subprocess output, payloads, passwords or keystore bytes.
        print("Setup stopped:", str(error) if isinstance(error, (RuntimeError, ValueError)) else "Required local files or permissions are unavailable.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
