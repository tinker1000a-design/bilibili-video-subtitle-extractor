#!/usr/bin/env python3
"""Install this repo's skill definition into the AI assistant's skill directory.

Renders `skills/video-digest/SKILL.md` with `{REPO}` replaced by this clone's
absolute path, then writes it into every skill directory detected on the
machine. Prints one line of JSON so an AI can report the result without
parsing prose.

Exit codes: 0 installed / already current, 1 error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import hashlib
import uuid
from file_io import atomic_text

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TEMPLATE = REPO / 'skills' / 'video-digest' / 'SKILL.md'
SKILL_NAME = 'video-digest'

# The template explains what {REPO} means, which stops making sense once the
# placeholder is gone. Swap that block for an "already installed" note.
REPO_NOTE = re.compile(r'<!-- REPO_NOTE -->.*?<!-- /REPO_NOTE -->', re.S)
INSTALLED_NOTE = (
    '本技能已安装在 `{repo}`，下文命令里的路径都是绝对路径，直接照抄即可。'
)

# User-level skill directories, with documented support for this file layout
# (`<name>/SKILL.md` + frontmatter `name`/`description`).
# Only parents that already exist are used, so we never litter a machine
# with directories for tools the user does not have.
#
# Agents without a skill directory (Cursor, opencode, plain Codex) still work:
# they read AGENTS.md at the repo root. See adapters/README.md.
CANDIDATES = [
    ('workbuddy', pathlib.Path.home() / '.workbuddy' / 'skills'),
    ('deepseek-harness', pathlib.Path.home() / '.dsh' / 'skills'),
    ('claude-code', pathlib.Path.home() / '.claude' / 'skills'),
    ('codex', pathlib.Path.home() / '.codex' / 'skills'),
    # Shared location read by dsh at lower priority; skipped when dsh's own
    # directory is present, so the same skill is not installed twice.
    ('agents-shared', pathlib.Path.home() / '.agents' / 'skills'),
]

def render() -> str:
    if not TEMPLATE.is_file():
        raise SystemExit(f'template missing: {TEMPLATE}')
    text = TEMPLATE.read_text(encoding='utf-8')
    if '{REPO}' not in text:
        raise SystemExit('template has no {REPO} placeholder; refusing to install a stale copy')
    if not REPO_NOTE.search(text):
        raise SystemExit('template is missing the REPO_NOTE block; refusing to install')
    # Use a callable: a raw Windows path in a replacement string would let
    # re interpret \_ and \v as escapes and silently corrupt the path.
    note = INSTALLED_NOTE.format(repo=REPO)
    text = REPO_NOTE.sub(lambda _m: note, text)
    return text.replace('{REPO}', str(REPO))


def plan_targets(explicit: list[str] | None):
    if explicit:
        return [(p, pathlib.Path(p).expanduser()) for p in explicit], False
    found = [(name, path) for name, path in CANDIDATES if path.is_dir()]
    # dsh reads ~/.agents/skills at lower priority; installing to both would
    # leave two copies of the same skill on disk.
    if any(name == 'deepseek-harness' for name, _ in found):
        found = [(name, path) for name, path in found if name != 'agents-shared']
    if found:
        return found, False
    return [], False


def install_one(name: str, parent: pathlib.Path, content: str, dry_run: bool, replace_existing=False):
    dest_dir = parent / SKILL_NAME
    dest = dest_dir / 'SKILL.md'
    entry = dict(host=name, path=str(dest))
    previous = None
    marker = dest_dir / '.video-digest-install.json'
    if dest.is_file():
        old = dest.read_text(encoding='utf-8')
        try:
            owner = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            owner = {}
        owned = (isinstance(owner, dict) and owner.get('repo') == str(REPO.resolve())
                 and owner.get('sha256') == hashlib.sha256(old.encode('utf-8')).hexdigest())
        if not owned and not replace_existing:
            entry['action'] = 'conflict'
            entry['hint'] = 'Existing skill is unowned, edited, or belongs to another clone; use --target and --replace-existing to replace it'
            return entry
        if old == content and owned:
            entry['action'] = 'unchanged'
            return entry
        previous = old
    if dry_run:
        entry['action'] = 'would_replace' if previous is not None else 'would_create'
        return entry
    dest_dir.mkdir(parents=True, exist_ok=True)
    if previous is not None:
        backup = dest_dir / ('SKILL.' + uuid.uuid4().hex + '.bak')
        atomic_text(backup, previous)
        entry['backup'] = str(backup)
    atomic_text(dest, content)
    atomic_text(marker, json.dumps(dict(repo=str(REPO.resolve()),
                                      sha256=hashlib.sha256(content.encode('utf-8')).hexdigest())))
    entry['action'] = 'replaced' if previous is not None else 'created'
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', action='append',
                        help='skill directory to install into (repeatable); default: auto-detect')
    parser.add_argument('--dry-run', action='store_true', help='report what would happen, write nothing')
    parser.add_argument('--check', action='store_true', help='only report existing installs, write nothing')
    parser.add_argument('--replace-existing', action='store_true',
                        help='explicitly replace conflicting skills in --target directories, keeping unique backups')
    args = parser.parse_args()
    if args.replace_existing and not args.target:
        parser.error('--replace-existing requires an explicit --target')

    content = render()

    if args.check:
        installed = []
        for name, parent in CANDIDATES:
            dest = parent / SKILL_NAME / 'SKILL.md'
            if dest.is_file():
                text = dest.read_text(encoding='utf-8', errors='replace')
                installed.append(dict(
                    host=name, path=str(dest),
                    points_here=str(REPO) in text,
                    current=text == content,
                ))
        print(json.dumps(dict(status='checked', repo=str(REPO), installed=installed),
                         ensure_ascii=False))
        return 0

    targets, _used_fallback = plan_targets(args.target)
    if not targets:
        print(json.dumps(dict(status='no_target', installed=[], first_time=False,
                              hint='No skill directory found; specify --target for your assistant')))
        return 1
    preview = [install_one(name, parent, content, True, args.replace_existing) for name, parent in targets]
    if any(r['action'] == 'conflict' for r in preview):
        print(json.dumps(dict(status='conflict', installed=preview, first_time=False), ensure_ascii=False))
        return 1
    results = preview if args.dry_run else [install_one(name, parent, content, False, args.replace_existing) for name, parent in targets]

    reused = [r for r in results if r['action'] in ('unchanged', 'replaced', 'would_replace')]
    fresh = [r for r in results if r['action'] in ('created', 'would_create')]
    if args.dry_run:
        status = 'dry_run'
    else:
        status = 'installed'

    print(json.dumps(dict(
        status=status,
        repo=str(REPO),
        installed=results,
        # 'first_time' is what tells the AI to print the usage tutorial.
        # Defined as "no host had it before": an existing install that merely
        # gets refreshed must not re-print the tutorial to a returning user.
        first_time=bool(fresh) and not reused and not args.dry_run,
        fallback_used=False,
    ), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
