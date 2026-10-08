#!/usr/bin/env python3
"""Assemble canonical skills and host overlays into a clean distributable bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("inference-stress-testing", "ray-autotune-inference", "inference-observability", "inference-optimization")
ALLOWED_ROOT = {"SKILL.md", "README.md", "compose.yaml", ".env.example", ".gitignore"}
ALLOWED_DIRS = {"scripts", "references", "tests", "agents"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".yaml"}


def included(relative):
    if len(relative.parts) == 1:
        return relative.name in ALLOWED_ROOT
    return (relative.parts[0] in ALLOWED_DIRS and relative.suffix in ALLOWED_SUFFIXES
            and not any(p.startswith(".") or p == "__pycache__" for p in relative.parts))


def build(output, root=ROOT, archive=False, format="copilot"):
    root, output = Path(root).resolve(), Path(output).resolve()
    scaffold = root / "plugins/inference-engineering"
    if format not in ("copilot", "portable"):
        raise ValueError("Unknown plugin format")
    if output.exists() or output.with_suffix(".zip").exists():
        raise ValueError("Choose a fresh output directory and ZIP filename")
    if output == root or root in output.parents and not output.is_relative_to(root / "dist"):
        raise ValueError("Build inside dist or outside the source repository")
    for name in SKILLS:
        if not (root / name / "SKILL.md").is_file():
            raise ValueError("Canonical skill missing")
    # Validate source payloads before creating output; never dereference symlinks.
    files = []
    for source in scaffold.rglob("*"):
        if source.is_symlink():
            raise ValueError("Scaffold symlinks are not distributable")
        if source.is_file() and (source.name in {"plugin.json", "README.md"} or source.suffix == ".md"):
            files.append((source, source.relative_to(scaffold)))
    for name in SKILLS:
        base = root / name
        for source in base.rglob("*"):
            relative = source.relative_to(base)
            if included(relative):
                if source.is_symlink():
                    raise ValueError("Skill symlinks are not distributable")
                if source.is_file():
                    files.append((source, Path("skills") / name / relative))
    marketplace = output.parent / ".agents/plugins/marketplace.json"
    copilot_marketplace = output.parent / "marketplace.json"
    if marketplace.exists() or copilot_marketplace.exists():
        raise ValueError("Marketplace already exists; choose a fresh build root")
    output.mkdir(parents=True)
    for source, relative in files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for source in (output / "agents").glob("*.md"):
        if not source.name.endswith(".agent.md"):
            source.rename(source.with_name(source.stem + ".agent.md"))
    if format == "portable":
        manifest = json.loads((output / "plugin.json").read_text())
        for key in ("agents", "skills", "commands"):
            manifest.pop(key, None)
        manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        (output / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for category in ("commands", "agents"):
            for source in (output / category).glob("*.md"):
                target = output / "com.github.copilot" / category / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    integrity = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "bundle-files.json").write_text(json.dumps(integrity, indent=2) + "\n")
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(json.dumps({"name": "inference-engineering-local",
        "interface": {"displayName": "Inference Engineering"}, "plugins": [{
            "name": "inference-engineering", "source": {"source": "local", "path": "./" + output.name},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools"}]}, indent=2) + "\n")
    manifest = json.loads((output / "plugin.json").read_text())
    copilot_marketplace.write_text(json.dumps({"name": "inference-engineering-local",
        "owner": {"name": "zetomatoz"}, "plugins": [{"name": "inference-engineering",
        "version": manifest["version"], "description": manifest["description"],
        "source": "./" + output.name}]}, indent=2) + "\n")
    if archive:
        with zipfile.ZipFile(output.with_suffix(".zip"), "x", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    bundle.write(path, Path(output.name) / path.relative_to(output))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--zip", action="store_true")
    parser.add_argument("--format", choices=("copilot", "portable"), default="copilot",
                        help="Copilot-compatible manifest by default; portable format optional")
    args = parser.parse_args()
    try:
        output = build(args.output, archive=args.zip, format=args.format)
    except (ValueError, OSError):
        print("Build failed; check source files and use a fresh build root.", file=sys.stderr)
        return 1
    print(f"Built plugin: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
