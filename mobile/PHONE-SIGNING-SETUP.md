# One-time signing setup using only an Android phone

Status: prepared for owner-run activation; no permanent key has been created by
Codex. No existing phone data, production service or GitHub signing secret has
been changed by preparing this code. Do not uninstall the old scanner.

The GitHub connector cannot administer signing secrets. These steps run on the
owner's phone, where GitHub authorisation and recovery passphrases stay private.
They affect only `android-experimental-signing` in
`rukminaiah-dot/nse-momentum-scanner` and the experimental branch.

## Install the local tools

Install Termux using the official project instructions:
https://github.com/termux/termux-app#installation
The F-Droid app page is https://f-droid.org/en/packages/com.termux/ .
If Termux is already installed, retain its installation and data; do not switch
installation sources by uninstalling it. Use its supported package repository.

Inside Termux, run these commands. No password or token belongs in chat.

```sh
pkg update
pkg install python openjdk-21 gh age git
git clone --depth 1 --branch experiment/android-paper-scanner https://github.com/rukminaiah-dot/nse-momentum-scanner.git nse-signing-setup
cd nse-signing-setup
python mobile/tools/phone_signing_setup.py create
python mobile/tools/phone_signing_setup.py backup
```

`create` retains an existing identity instead of regenerating it. The raw key
and its random password are stored with private permissions outside the checkout,
in Termux's own storage. Only the public certificate SHA256 is displayed.

`backup` asks **inside Termux** for an age recovery passphrase, then asks again to
decrypt the recovery copy and compares all recovered bytes. Retain this recovery
passphrase separately in your password manager. The encrypted backup contains the
PKCS12 keystore, its password and public identity metadata. No raw archive is
written to shared storage.

## Keep a recovery copy outside Termux

After backup verification, allow Termux storage access and copy **only** the
age-encrypted recovery file to a durable location you control:

```sh
termux-setup-storage
cp ~/.local/share/nse-paper-signing/android-signing-backup.age ~/storage/shared/Download/android-signing-recovery.age
```

Save a further private copy using your file manager/cloud backup. Do not upload
it to the repository, chat, Actions artifacts or caches. Never copy the raw
`.p12` or `password.txt` out of Termux. Do not uninstall Termux or clear its data
until recovery is independently verified and the encrypted backup is retained.

To recover on a new Termux installation, install the tools and checkout again,
then use the original backup and its original recovery passphrase:

```sh
python mobile/tools/phone_signing_setup.py restore --backup ~/storage/shared/Download/android-signing-recovery.age
```

Restore verifies the recovered certificate before retaining the files, refuses
to overwrite any existing identity, and never generates a replacement key.

## Configure the dedicated GitHub environment

Use GitHub's browser authorisation on this phone:

```sh
gh auth login --web --hostname github.com --git-protocol https
python mobile/tools/phone_signing_setup.py configure
```

The helper asks you to confirm the encrypted backup is retained outside Termux.
It preserves an existing environment's settings, pins the public certificate,
and supplies the four signing secrets to `gh secret set` through standard input.
It never places secrets in command arguments or prints their values. Existing
matching configuration is reused; conflicting identities or unpinned existing
signing secrets stop setup. An interrupted setup can fill only missing secrets.

The new public variable is `ANDROID_SIGNING_CERT_SHA256`. The private secrets are
`ANDROID_KEYSTORE_BASE64`, `ANDROID_SIGNING_STORE_PASSWORD`,
`ANDROID_SIGNING_KEY_ALIAS` and `ANDROID_SIGNING_KEY_PASSWORD`.
No production environment, Upstox secret, merge or public release is involved.

## Request the first signed candidate

```sh
python mobile/tools/phone_signing_setup.py build
gh run list --repo rukminaiah-dot/nse-momentum-scanner --workflow android-private-candidate.yml --branch experiment/android-paper-scanner
```

`build` first checks the remote signing identity. It creates an empty commit on
only the experimental branch to trigger the push workflow; app and production
code are unchanged by that commit. This works without putting the new workflow
on `main`. If the branch changes concurrently, the ref update fails safely.

The workflow runs the full offline Python suite and all Android unit tests
before release packaging. It verifies the APK signature and certificate pin,
rejects a debug package and records public metadata. The output artifact is
`android-permanent-signed-candidate`; it contains only the APK and public report.
Private key material is deleted from the runner and is never an artifact/cache.
If signing is absent, the workflow clearly reports pending and builds no signed
candidate. A green readiness job is not proof of a signed artifact.

## First install and future updates

- Permanent candidate: `com.nsemomentum.paper.scanner` — Momentum Paper Scanner.
- Disposable test build: `com.nsemomentum.paper.scanner.dev` — Momentum Scanner Test.
- Historical installations: `com.nsemomentum.paper` and
  `com.nsemomentum.paper.preview`, with separate private data.

The permanent candidate installs alongside historical apps. It cannot read their
private data. Migration requires an export that the old app itself supports.
Preserve the old installation if it has no export feature.

Before recommending regular use, install two successive privately signed builds
and verify that selections, settings, token access and paper history survive.
The metadata verifier can compare two APKs with `--previous-apk`; this checks
identity/version compatibility, not actual phone data preservation.

The in-app update button needs an explicitly approved published release and
update manifest. That channel is not published by these setup steps. Android
still asks the user to approve installation. Live Upstox and phone background
operation remain separate validations.

Official references:
- https://developer.android.com/studio/publish/app-signing
- https://cli.github.com/manual/gh_secret_set
- https://cli.github.com/manual/gh_auth_login
- https://github.com/FiloSottile/age
