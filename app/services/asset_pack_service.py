"""Server-hosted custom assets: reaction pop-up emojis and stickers, each with a "standard" and an
"nsfw" (mature) folder.

Layout, under the `assets_root` setting (a host bind-mount — see docker-compose.yml — kept out of
git, the Docker image and `media_root`, whose files nginx serves directly and unauthenticated):

    <assets_root>/reactions/standard/[<style>/]*.png
    <assets_root>/reactions/nsfw/[<style>/]*.png
    <assets_root>/stickers/standard/[<style>/]*.png
    <assets_root>/stickers/nsfw/[<style>/]*.png

Each tier folder may hold PNGs directly *and* one level of "style" subfolders (e.g.
`nsfw/cartoon/kiss.png`) purely for the owner's own file management — the app shows no folder
labels. Anything deeper is ignored. An asset's id is its path below the tier folder without `.png`:
`kiss` or `cartoon/kiss`. Adding an asset is just copying a PNG into the right place: no deploy, no
code change, no allow-list to edit on either side.

Every segment of an id goes through [SEGMENT_PATTERN] first, `kind`/`tier` are closed enums, the
resolved path must equal the expected non-symlinked path inside the tier folder, and a request only
succeeds if the file actually exists — together that rules out path traversal (`..`, `/`, absolute
paths) and symlink escapes. A file or folder that doesn't meet the naming rule is skipped, with a
logged warning (once per path) so a bad name isn't a silent failure.
"""

import logging
import re
from enum import Enum
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# One path segment (a style folder name or a file stem): lowercase letters/digits plus `_`/`-`. No
# dots or slashes, so a segment can never escape the directory or smuggle in an extension.
SEGMENT_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")

# At most `style/name`: files directly in the tier folder, or one level of subfolder below it.
MAX_ID_SEGMENTS = 2

_EXTENSION = ".png"


class AssetKind(str, Enum):
    REACTIONS = "reactions"
    STICKERS = "stickers"


class AssetTier(str, Enum):
    STANDARD = "standard"
    NSFW = "nsfw"


# WS `reaction.send` effect names for custom reaction emojis: `<prefix><id>`. A `:` can't appear in
# a built-in effect name or in an id, so the prefixes are unambiguous. `nsfw:` predates the
# standard folder and is kept as-is so already-installed clients keep working.
REACTION_EFFECT_PREFIXES: dict[str, AssetTier] = {
    "std:": AssetTier.STANDARD,
    "nsfw:": AssetTier.NSFW,
}

# Paths already warned about, so listing on every request doesn't repeat the same warning forever.
_warned_paths: set[str] = set()


def _warn_skipped(path: Path, reason: str) -> None:
    key = str(path)
    if key in _warned_paths:
        return
    _warned_paths.add(key)
    logger.warning("skipping %s in assets folder: %s", path, reason)


def asset_dir(kind: AssetKind, tier: AssetTier) -> Path:
    return Path(get_settings().assets_root) / kind.value / tier.value


def _natural_key(segment: str) -> list[tuple[int, int, str]]:
    # `sticker-2` sorts before `sticker-10` (plain string order would put `-10` first).
    return [
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"(\d+)", segment)
        if part
    ]


def _sort_key(asset_id: str) -> list[list[tuple[int, int, str]]]:
    # Compared folder first, then file name: `3d/x` < `cartoon/a` < `cartoon/b` < `emoji/a`, and a
    # file directly in the tier folder interleaves with the folders purely by name.
    return [_natural_key(segment) for segment in asset_id.split("/")]


def is_valid_asset_id(asset_id: str) -> bool:
    segments = asset_id.split("/")
    return len(segments) <= MAX_ID_SEGMENTS and all(SEGMENT_PATTERN.match(s) for s in segments)


def _png_stems(directory: Path) -> list[str]:
    """The valid `.png` stems directly inside [directory]; warns about anything else that looks
    like an asset but can't be used."""
    stems: list[str] = []
    for path in directory.iterdir():
        if path.is_symlink():
            _warn_skipped(path, "symlinks are not followed")
        elif path.is_file() and path.suffix == _EXTENSION:
            if SEGMENT_PATTERN.match(path.stem):
                stems.append(path.stem)
            else:
                _warn_skipped(path, "name must be lowercase letters, digits, '_' or '-' (max 64)")
        elif path.is_file():
            _warn_skipped(path, "only .png files are used")
    return stems


def list_ids(kind: AssetKind, tier: AssetTier) -> list[str]:
    directory = asset_dir(kind, tier)
    if not directory.is_dir():
        return []
    ids = list(_png_stems(directory))
    for style in directory.iterdir():
        if style.is_symlink() or not style.is_dir():
            continue
        if not SEGMENT_PATTERN.match(style.name):
            _warn_skipped(style, "folder name must be lowercase letters, digits, '_' or '-' (max 64)")
            continue
        ids.extend(f"{style.name}/{stem}" for stem in _png_stems(style))
        for deeper in style.iterdir():
            if deeper.is_dir() and not deeper.is_symlink():
                _warn_skipped(deeper, "only one level of subfolders is supported")
    return sorted(ids, key=_sort_key)


def path_for(kind: AssetKind, tier: AssetTier, asset_id: str) -> Path | None:
    """The PNG for [asset_id], or None if the id is malformed or no such file exists."""
    if not is_valid_asset_id(asset_id):
        return None
    segments = asset_id.split("/")
    base = asset_dir(kind, tier)
    path = base.joinpath(*segments[:-1], f"{segments[-1]}{_EXTENSION}")
    if not path.is_file():
        return None
    # Belt and braces on top of the segment check: the fully resolved path must be exactly the
    # expected location inside the (resolved) tier folder — which also rejects any symlink hop.
    expected = base.resolve().joinpath(*segments[:-1], f"{segments[-1]}{_EXTENSION}")
    return path if path.resolve() == expected else None


def is_valid_reaction_effect(effect: object) -> bool:
    """Whether a WS reaction `effect` names an existing custom reaction (`std:<id>`/`nsfw:<id>`)."""
    if not isinstance(effect, str):
        return False
    for prefix, tier in REACTION_EFFECT_PREFIXES.items():
        if effect.startswith(prefix):
            return path_for(AssetKind.REACTIONS, tier, effect[len(prefix):]) is not None
    return False
