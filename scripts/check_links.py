#!/usr/bin/env python3
"""Check repository Markdown links and explicit static file references."""
import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def anchors(path):
    """GitHub heading IDs, including duplicate heading suffixes."""
    result = set()
    counts = {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', path.read_text(), re.M):
        heading = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', heading)
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        result.add(slug if not number else f'{slug}-{number}')
    result.update(re.findall(r'(?:id|name)=["\']([^"\']+)', path.read_text()))
    return result


def check(root, external=False):
    errors, urls = [], set()
    count = 0
    for path in sorted(root.rglob('*.md')):
        if any(part in {'.git', 'artifacts', 'node_modules', '.cache'} for part in path.relative_to(root).parts):
            continue
        source = path.read_text()
        # Code examples can contain illustrative Markdown; only prose defines links.
        prose = re.sub(r'```.*?```', '', source, flags=re.S)
        definitions = dict((key.lower().strip(), value) for key, value in
                           re.findall(r'^\s*\[([^]]+)\]:\s*<?([^\s>]+)>?', prose, re.M))
        links = re.findall(r'!?\[[^]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)', prose)
        for label, key in re.findall(r'!?\[([^]]+)\]\[([^]]*)\]', prose):
            key = (key or label).lower().strip()
            if key not in definitions:
                errors.append(f'{path.relative_to(root)}: undefined reference [{key}]')
            else:
                links.append(definitions[key])
        links.extend(definitions.values())
        links.extend(re.findall(r'<(https?://[^>]+)>', prose))
        # Inline static paths and paths in runnable snippets use the skill directory.
        base = path.parent
        # Runnable snippets resolve relative to their containing skill directory.
        for parent in (path.parent, *path.parents):
            if parent == root:
                break
            if (parent / 'SKILL.md').is_file():
                base = parent
                break
        static = re.findall(r'(?<![\w/])(?:references|scripts|tests)/[\w./-]+\.(?:md|py|json)\b', source)
        static.extend(re.findall(r'`(README\.md|\.env\.example|compose\.yaml)`', source))
        for reference in set(static):
            count += 1
            if not (base / reference).is_file():
                errors.append(f'{path.relative_to(root)}: missing file reference {reference}')
        for link in links:
            count += 1
            link = link.strip('<>')
            parsed = urlsplit(link)
            if parsed.scheme in {'http', 'https'}:
                urls.add(link)
                continue
            if parsed.scheme:
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.exists():
                errors.append(f'{path.relative_to(root)}: broken link {link}')
            elif parsed.fragment and target.suffix == '.md' and unquote(parsed.fragment) not in anchors(target):
                errors.append(f'{path.relative_to(root)}: missing anchor {link}')
    if external:
        for url in sorted(urls):
            result = subprocess.run(['curl', '--location', '--silent', '--show-error',
                                     '--output', '/dev/null', '--write-out', '%{http_code}',
                                     '--connect-timeout', '10', '--max-time', '30', '--retry', '2', url],
                                    capture_output=True, text=True)
            if result.returncode or not result.stdout.startswith('2'):
                errors.append(f'{url}: HTTP {result.stdout or "unavailable"} {result.stderr.strip()}')
    return count, len(urls), errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', action='store_true', help='Also check public HTTP links using curl')
    args = parser.parse_args()
    count, urls, errors = check(ROOT, args.external)
    for error in errors:
        print(error)
    print(f'Checked {count} links/file references and {urls} unique public URLs: {len(errors)} errors')
    raise SystemExit(bool(errors))
