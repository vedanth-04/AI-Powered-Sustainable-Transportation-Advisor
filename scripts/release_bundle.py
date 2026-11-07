"""Transfer the approved Phase 2 v1 model bundle through GitHub Actions secrets."""

import argparse
from base64 import b64decode, b64encode
from hashlib import sha256
from io import BytesIO
from lzma import LZMAError
import os
from pathlib import Path
import subprocess
from zipfile import BadZipFile, ZIP_LZMA, ZipFile, ZipInfo


DEFAULT_BUNDLE_DIR = Path(__file__).resolve().parents[1] / "outputs" / "phase2_serving"
SECRET_NAMES = ("PHASE2_MODEL_V1_PART_1", "PHASE2_MODEL_V1_PART_2")
PART_LIMIT = 48_000
APPROVED_FILES = {
    "manifest.json": (593, "4e5e853c3849ad55cc69d7134753e3b72bb52f72bc05963f60c5e122c4585029"),
    "model.joblib": (247_067, "b26d1a45f8e97278b8be70eef9c6c88e39b7d52537d55bea6a206b3391934a88"),
}


def verify_file(name: str, content: bytes) -> bytes:
    size, digest = APPROVED_FILES[name]
    if len(content) != size or sha256(content).hexdigest() != digest:
        raise ValueError(f"{name} does not match the approved Phase 2 v1 bundle.")
    return content


def pack_bundle(bundle_dir: Path) -> tuple[bytes, bytes]:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        for name, (size, _) in APPROVED_FILES.items():
            with (bundle_dir / name).open("rb") as source:
                content = verify_file(name, source.read(size + 1))
            # Fixed ZIP metadata makes retries send the same parts for the same bundle.
            entry = ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content, compress_type=ZIP_LZMA)

    encoded = b64encode(archive_bytes.getvalue())
    if len(encoded) > PART_LIMIT * len(SECRET_NAMES):
        raise ValueError("The approved bundle does not fit in two GitHub Actions secrets.")
    midpoint = (len(encoded) + 1) // 2
    return encoded[:midpoint], encoded[midpoint:]


def upload_bundle(bundle_dir: Path, repo: str) -> None:
    for name, part in zip(SECRET_NAMES, pack_bundle(bundle_dir)):
        try:
            subprocess.run(
                ["gh", "secret", "set", name, "--repo", repo],
                input=part,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                f"Could not set {name}. Check GitHub CLI authentication and repository access, "
                "then retry the upload."
            ) from exc


def unpack_bundle() -> dict[str, bytes]:
    parts = []
    for name in SECRET_NAMES:
        part = "".join(os.environ.get(name, "").split())
        if not part or len(part) > PART_LIMIT:
            raise ValueError(f"{name} is missing or exceeds the per-secret size limit.")
        parts.append(part)
    try:
        compressed = b64decode("".join(parts), validate=True)
    except ValueError as exc:
        raise ValueError("The Phase 2 bundle secrets are not valid Base64.") from exc

    try:
        with ZipFile(BytesIO(compressed)) as archive:
            if sorted(archive.namelist()) != sorted(APPROVED_FILES):
                raise ValueError("The bundle archive must contain exactly manifest.json and model.joblib.")
            bundle = {}
            for name, (size, _) in APPROVED_FILES.items():
                entry = archive.getinfo(name)
                if entry.file_size != size or entry.compress_type != ZIP_LZMA:
                    raise ValueError(f"{name} has unexpected archive metadata.")
                with archive.open(entry) as source:
                    bundle[name] = verify_file(name, source.read(size + 1))
            return bundle
    except (BadZipFile, LZMAError, EOFError, RuntimeError) as exc:
        raise ValueError("The Phase 2 bundle archive is invalid.") from exc


def stage_bundle(bundle_dir: Path) -> None:
    bundle = unpack_bundle()
    bundle_dir.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in bundle.items():
            (bundle_dir / name).write_bytes(content)
    except OSError:
        for name in bundle:
            (bundle_dir / name).unlink(missing_ok=True)
        bundle_dir.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    upload = commands.add_parser("upload", help="Set both secrets using the authenticated GitHub CLI.")
    upload.add_argument("--repo", required=True, metavar="OWNER/REPO")
    upload.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    stage = commands.add_parser("stage", help="Verify both secrets and write the approved bundle.")
    stage.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    args = parser.parse_args()

    try:
        if args.command == "upload":
            upload_bundle(args.bundle_dir, args.repo)
            print(f"Set both Phase 2 v1 bundle secrets in {args.repo}.")
        else:
            stage_bundle(args.bundle_dir)
            print(f"Staged the verified Phase 2 v1 bundle at {args.bundle_dir.resolve()}")
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Phase 2 bundle {args.command} failed: {exc}\n")


if __name__ == "__main__":
    main()
