"""Explicit, one-time download; normal inference only reads local files."""
import argparse

from ml.constants import EMBEDDING_MODEL_ID


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the MeLawDy embedding model")
    parser.add_argument("--output-dir", default="models/bge-m3-russian-legal")
    parser.add_argument("--revision", default="main", help="Use a commit hash to pin the model")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=EMBEDDING_MODEL_ID, local_dir=args.output_dir, revision=args.revision,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"],
    )
    print(f"Model saved to {path}")


if __name__ == "__main__":
    main()
