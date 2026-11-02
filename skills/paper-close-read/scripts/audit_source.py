"""List lexical/paragraph risks without modifying or certifying the source."""
import argparse
import json
from pathlib import Path
from source_quality import source_risks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fulltext', type=Path)
    args = parser.parse_args()
    data = json.loads(args.fulltext.read_text(encoding='utf-8-sig'))
    print(json.dumps({'notice': 'Candidates only; check original pages. No automatic repairs.',
                      'risks': source_risks(data)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
