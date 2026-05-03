# Generate Post

Generate or update the daily digest post using `scripts/generate_post.py`.

## Prerequisites

The script requires `pyyaml`. The dependency is listed in `pyproject.toml`. If not yet installed:

```
uv sync
```

## Usage

The script takes YAML input describing articles and writes a dated markdown post to `docs/_posts/`.

### From a YAML file

```
uv run python scripts/generate_post.py --input <path/to/articles.yaml>
```

### From stdin

```
cat articles.yaml | uv run python scripts/generate_post.py --stdin
```

### Options

| Flag | Description |
|------|-------------|
| `--input`, `-i` | Path to input YAML file |
| `--stdin` | Read YAML from stdin |
| `--output-dir`, `-o` | Output directory (default: `docs/_posts`) |
| `--date` | Override date in `YYYY-MM-DD` format |
| `--dry-run` | Print output without writing to file |

## YAML Input Format

```yaml
date: 2026-05-03          # optional, defaults to today
articles:
  - id: "a1b2c3d4"        # required, hex string for deduplication
    title: "Article Title"
    url: "https://example.com/article"
    source: "来源名称"
    summary: "文章摘要内容"
    tags: ["标签1", "标签2"]
    category: tech         # optional, see category aliases below
    rating: 4              # optional, 1-5 stars
    processed_at: "2026-05-03T10:30:00+08:00"  # optional
```

### Category Aliases

| Input | Mapped To |
|-------|-----------|
| `tech`, `technology`, `技术` | Tech |
| `business` | 商业 |
| `ai` | AI |
| `international` | 国际 |
| `science` | 科学 |
| `health` | 健康 |
| `culture` | 文化 |
| `sports` | 体育 |
| `politics` | 政治 |
| `economy` | 经济 |
| `environment` | 环境 |
| (anything else) | Other |

## Behavior

- If no post exists for the date, a new one is created with front matter and categorized articles.
- If a post already exists, new articles are merged in — articles with duplicate `id` values are skipped.
- Output files are named `{date}-daily-digest.md` and written atomically (via temp file + rename).
