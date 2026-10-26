"""Write the release checksum, failing the build on any read or write error."""
import argparse
import hashlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.installer.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    args.output.write_text(f'{digest}  {args.installer.name}\n', encoding='ascii', newline='\n')
    print('SHA-256:', digest)


if __name__ == '__main__':
    main()
