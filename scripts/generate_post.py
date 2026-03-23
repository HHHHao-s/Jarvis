#!/usr/bin/env python3
import argparse
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

ARTICLE_ID_RE = re.compile(r'<!-- article-id: ([a-f0-9]+) -->')
FRONT_MATTER_RE = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)
CATEGORY_RE = re.compile(r'^## (.+)$', re.MULTILINE)

CATEGORY_ALIASES = {
    'tech': 'Tech',
    'technology': 'Tech',
    '技术': 'Tech',
    'business': '商业',
    'ai': 'AI',
    'international': '国际',
    'science': '科学',
    'health': '健康',
    'culture': '文化',
    'sports': '体育',
    'politics': '政治',
    'economy': '经济',
    'environment': '环境',
    'other': 'Other',
}

POSTS_DIR = Path(__file__).parent.parent / 'docs' / '_posts'


def normalize_category(cat: str) -> str:
    return CATEGORY_ALIASES.get(cat.lower(), cat)


def parse_args():
    p = argparse.ArgumentParser(description='Generate/update daily digest markdown from YAML')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--input', '-i', help='Input YAML file path')
    g.add_argument('--stdin', action='store_true', help='Read YAML from stdin')
    p.add_argument('--output-dir', '-o', help='Output directory (default: docs/_posts)')
    p.add_argument('--date', help='Override date YYYY-MM-DD')
    p.add_argument('--dry-run', action='store_true', help='Print output without writing')
    return p.parse_args()


def load_data(args) -> dict:
    if args.stdin:
        return yaml.safe_load(sys.stdin)
    if args.input:
        with open(args.input, encoding='utf-8') as f:
            return yaml.safe_load(f)
    raise ValueError('Specify --input FILE or --stdin')


def parse_existing(path: Path):
    if not path.exists():
        return {}, set(), ''
    content = path.read_text(encoding='utf-8')
    fm_match = FRONT_MATTER_RE.match(content)
    front_matter = {}
    if fm_match:
        try:
            front_matter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            pass
    existing_ids = set(ARTICLE_ID_RE.findall(content))
    return front_matter, existing_ids, content


def format_article(article: dict) -> str:
    tags_str = ' '.join(f'`{t}`' for t in article.get('tags', []))
    processed_at = article.get('processed_at', '')
    time_str = ''
    if processed_at:
        try:
            dt = datetime.fromisoformat(processed_at)
            time_str = dt.strftime('%H:%M')
        except ValueError:
            pass
    if not time_str:
        tz8 = timezone(timedelta(hours=8))
        time_str = datetime.now(tz8).strftime('%H:%M')

    rating = article.get('rating', 0)
    stars = '⭐' * int(rating) if rating else ''
    rating_str = f' &nbsp;|&nbsp; **评分**: {stars}' if stars else ''

    meta = f'**来源**: {article["source"]} &nbsp;|&nbsp; **标签**: {tags_str} &nbsp;|&nbsp; **时间**: {time_str}{rating_str}'
    return (
        f'<!-- article-id: {article["id"]} -->\n'
        f'### [{article["title"]}]({article["url"]})\n'
        f'{meta}\n'
        f'> {article["summary"]}\n'
        '\n'
        '---\n'
    )


def build_new_content(date: str, articles: list) -> str:
    all_tags = []
    seen_tags = set()
    for a in articles:
        for t in a.get('tags', []):
            if t not in seen_tags:
                all_tags.append(t)
                seen_tags.add(t)

    fm = {
        'title': f'全球日报 {date}',
        'date': f'{date} 00:00:00 +0800',
        'categories': ['Daily Digest'],
        'tags': all_tags[:15],
        'toc': True,
    }
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    by_cat: dict[str, list] = {}
    for a in articles:
        cat = normalize_category(a.get('category', 'Other'))
        by_cat.setdefault(cat, []).append(a)

    body = ''
    for cat, arts in by_cat.items():
        body += f'\n## {cat}\n\n'
        for a in arts:
            body += format_article(a) + '\n'

    return f'---\n{fm_str}\n---\n{body}'


def merge_into_existing(existing_content: str, existing_fm: dict, existing_ids: set, new_articles: list, date: str) -> str:
    fm_match = FRONT_MATTER_RE.match(existing_content)
    body_start = fm_match.end() if fm_match else 0
    body = existing_content[body_start:]

    all_tags = list(existing_fm.get('tags', []))
    seen_tags = set(all_tags)
    for a in new_articles:
        for t in a.get('tags', []):
            if t not in seen_tags:
                all_tags.append(t)
                seen_tags.add(t)

    new_fm = dict(existing_fm)
    new_fm['tags'] = all_tags[:15]
    if 'toc' not in new_fm:
        new_fm['toc'] = True

    fm_str = yaml.dump(new_fm, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    by_cat: dict[str, list] = {}
    for a in new_articles:
        cat = normalize_category(a.get('category', 'Other'))
        by_cat.setdefault(cat, []).append(a)

    existing_cats = {m.group(1): m.start() for m in CATEGORY_RE.finditer(body)}

    for cat, arts in by_cat.items():
        new_block = ''
        for a in arts:
            new_block += format_article(a) + '\n'

        if cat in existing_cats:
            cat_pos = existing_cats[cat]
            next_cat_positions = [p for c, p in existing_cats.items() if p > cat_pos]
            if next_cat_positions:
                insert_pos = min(next_cat_positions)
                body = body[:insert_pos] + new_block + body[insert_pos:]
            else:
                if not body.endswith('\n'):
                    body += '\n'
                body += new_block
            existing_cats = {m.group(1): m.start() for m in CATEGORY_RE.finditer(body)}
        else:
            if not body.endswith('\n'):
                body += '\n'
            body += f'\n## {cat}\n\n{new_block}'
            existing_cats = {m.group(1): m.start() for m in CATEGORY_RE.finditer(body)}

    return f'---\n{fm_str}\n---\n{body}'


def atomic_write(path: Path, content: str):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.rename(path)


def main():
    args = parse_args()

    try:
        data = load_data(args)
    except (ValueError, yaml.YAMLError, FileNotFoundError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)

    date = args.date or data.get('date') or datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    articles = data.get('articles', [])

    if not articles:
        print('No articles in input, nothing to do.')
        sys.exit(0)

    output_dir = Path(args.output_dir) if args.output_dir else POSTS_DIR
    output_path = output_dir / f'{date}-daily-digest.md'

    existing_fm, existing_ids, existing_content = parse_existing(output_path)

    new_articles = [a for a in articles if a.get('id') and a['id'] not in existing_ids]
    skipped = len(articles) - len(new_articles)

    if not new_articles:
        print(f'All {skipped} article(s) already exist, nothing to write.')
        sys.exit(0)

    if existing_content:
        content = merge_into_existing(existing_content, existing_fm, existing_ids, new_articles, date)
    else:
        content = build_new_content(date, new_articles)

    if args.dry_run:
        print(content)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(output_path, content)
        print(f'SUCCESS: {output_path}')

    print(f'Added: {len(new_articles)}, Skipped (duplicate): {skipped}')


if __name__ == '__main__':
    main()
