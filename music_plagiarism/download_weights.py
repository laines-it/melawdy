"""Download only the original, pinned Mippia checkpoints. GPL-3.0."""
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request

from core import ROOT, VENDOR, COMMIT, file_hash


def download():
    manifest = json.loads((ROOT / "UPSTREAM.json").read_text())
    for item in manifest["weights"]:
        target = VENDOR / item["path"]
        if target.is_file() and file_hash(target) == item["sha256"]:
            print(f"Verified: {item['path']}")
            continue
        url = f"https://raw.githubusercontent.com/Mippia/Music-Plagiarism-Detection/{COMMIT}/{item['path']}"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                digest = hashlib.sha256()
                size = 0
                with urllib.request.urlopen(url, timeout=60) as response:
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > item["size"]:
                            raise ValueError(f"Unexpected checkpoint size: {item['path']}")
                        stream.write(block)
                        digest.update(block)
            if size != item["size"] or digest.hexdigest() != item["sha256"]:
                raise ValueError(f"Checkpoint checksum mismatch: {item['path']}")
            temporary.replace(target)
            print(f"Downloaded and verified: {item['path']}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    download()
