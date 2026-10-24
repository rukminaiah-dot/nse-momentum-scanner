#!/usr/bin/env python3
"""Verify a candidate against the permanent identity before offering it for installation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PACKAGE = "com.nsemomentum.paper.scanner"


def inspect(apk, build_tools):
    result = subprocess.run([str(build_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(apk)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("APK signature verification failed.")
    signers = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})", result.stdout)
    if len(signers) != 1:
        raise ValueError("Expected exactly one verified APK signing certificate.")
    badging = subprocess.run([str(build_tools / "aapt"), "dump", "badging", str(apk)], capture_output=True, text=True, check=False)
    match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging.stdout)
    if badging.returncode or not match:
        raise ValueError("APK package metadata is invalid.")
    if "application-debuggable" in badging.stdout:
        raise ValueError("Debug APK cannot enter the permanent release channel.")
    return {"packageName": match[1], "versionCode": int(match[2]), "versionName": match[3], "signingSha256": signers[0].lower()}


def validate(candidate, expected_sha256, previous=None, package=PACKAGE):
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256 or ""):
        raise ValueError("Permanent public signing fingerprint is missing or invalid.")
    if candidate["packageName"] != package or candidate["signingSha256"] != expected_sha256.lower() or candidate["versionCode"] <= 0:
        raise ValueError("Candidate differs from the permanent package or signing identity.")
    if previous:
        if previous["packageName"] != package or previous["signingSha256"] != candidate["signingSha256"]:
            raise ValueError("Previous installation uses an incompatible package or signing identity.")
        if candidate["versionCode"] <= previous["versionCode"]:
            raise ValueError("An update must increase the installed version code.")
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--build-tools", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--previous-apk", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--commit", default="")
    args = parser.parse_args()
    candidate = inspect(args.apk, args.build_tools)
    previous = inspect(args.previous_apk, args.build_tools) if args.previous_apk else None
    report = dict(validate(candidate, args.expected_sha256, previous), sha256=hashlib.sha256(args.apk.read_bytes()).hexdigest(), commit=args.commit,
                  previousApkChecked=previous is not None, deviceUpdateVerified=False)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("Candidate package, signature and pinned certificate verified. Device update testing is still required.")


if __name__ == "__main__":
    main()
