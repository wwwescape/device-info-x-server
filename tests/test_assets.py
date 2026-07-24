import logging

import pytest

from app.services import asset_pack_service
from app.services.asset_pack_service import AssetKind, AssetTier
from tests.conftest import auth_headers

_PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def assets_root(tmp_path, monkeypatch):
    """Points the service at a temp `<root>/{reactions,stickers}/{standard,nsfw}` tree; the returned
    helper writes a file (creating any style subfolder) at `<kind>/<tier>/<name>`."""
    monkeypatch.setattr(
        asset_pack_service,
        "asset_dir",
        lambda kind, tier: tmp_path / kind.value / tier.value,
    )
    asset_pack_service._warned_paths.clear()

    def put(kind: str, tier: str, name: str, content: bytes = _PNG) -> None:
        path = tmp_path / kind / tier / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    put.root = tmp_path  # type: ignore[attr-defined]
    return put


async def test_list_requires_pairing(client, alice):
    r = await client.get("/api/v1/assets/reactions", headers=auth_headers(alice))
    assert r.status_code == 409


async def test_list_is_naturally_sorted_and_png_only(client, paired, assets_root):
    alice, _bob = paired
    for name in ("s-10.png", "s-2.png", "s-1.png", "notes.txt", "Bad Name.png"):
        assets_root("stickers", "standard", name)

    r = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    assert r.json() == {"standard": ["s-1", "s-2", "s-10"], "nsfw": []}


async def test_style_folders_are_listed_in_folder_then_file_order(client, paired, assets_root):
    alice, _bob = paired
    names = (
        "emoji/b.png",
        "emoji/a.png",
        "3d/z.png",
        "cartoon/a-10.png",
        "cartoon/a-2.png",
        "kiss.png",
        "zzz.png",
    )
    for name in names:
        assets_root("reactions", "nsfw", name)

    r = await client.get("/api/v1/assets/reactions", params={"mature": "true"}, headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    # Purely by full relative path: root files interleave with the folders by name.
    assert r.json()["nsfw"] == [
        "3d/z",
        "cartoon/a-2",
        "cartoon/a-10",
        "emoji/a",
        "emoji/b",
        "kiss",
        "zzz",
    ]


async def test_style_folders_work_in_both_tiers_and_kinds(client, paired, assets_root):
    alice, _bob = paired
    assets_root("stickers", "standard", "cute/hug.png")
    assets_root("reactions", "standard", "cute/wave.png")
    stickers = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    reactions = await client.get("/api/v1/assets/reactions", headers=auth_headers(alice))
    assert stickers.json()["standard"] == ["cute/hug"]
    assert reactions.json()["standard"] == ["cute/wave"]


async def test_nsfw_only_listed_when_mature_requested(client, paired, assets_root):
    alice, _bob = paired
    assets_root("reactions", "standard", "wave.png")
    assets_root("reactions", "nsfw", "spicy.png")
    assets_root("reactions", "nsfw", "cartoon/spicier.png")

    off = await client.get("/api/v1/assets/reactions", headers=auth_headers(alice))
    on = await client.get("/api/v1/assets/reactions", params={"mature": "true"}, headers=auth_headers(alice))
    assert off.json() == {"standard": ["wave"], "nsfw": []}
    assert on.json() == {"standard": ["wave"], "nsfw": ["cartoon/spicier", "spicy"]}


async def test_a_second_folder_level_is_ignored_with_a_warning(client, paired, assets_root, caplog):
    alice, _bob = paired
    assets_root("stickers", "standard", "ok/fine.png")
    assets_root("stickers", "standard", "ok/deeper/hidden.png")

    with caplog.at_level(logging.WARNING, logger=asset_pack_service.logger.name):
        r = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    assert r.json()["standard"] == ["ok/fine"]
    assert "only one level of subfolders" in caplog.text


async def test_invalid_names_are_skipped_with_a_warning_once(client, paired, assets_root, caplog):
    alice, _bob = paired
    assets_root("stickers", "standard", "Cartoon Style/kiss.png")
    assets_root("stickers", "standard", "good/Bad Name.png")
    assets_root("stickers", "standard", "good/fine.png")

    with caplog.at_level(logging.WARNING, logger=asset_pack_service.logger.name):
        for _ in range(2):
            r = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    assert r.json()["standard"] == ["good/fine"]
    assert caplog.text.count("Cartoon Style") == 1  # not repeated on the second request
    assert "Bad Name.png" in caplog.text


async def test_kinds_are_separate(client, paired, assets_root):
    alice, _bob = paired
    assets_root("reactions", "standard", "a.png")
    assets_root("stickers", "standard", "b.png")
    reactions = await client.get("/api/v1/assets/reactions", headers=auth_headers(alice))
    stickers = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    assert reactions.json()["standard"] == ["a"]
    assert stickers.json()["standard"] == ["b"]


async def test_list_is_empty_when_directories_missing(client, paired, assets_root):
    alice, _bob = paired
    r = await client.get("/api/v1/assets/stickers", params={"mature": "true"}, headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json() == {"standard": [], "nsfw": []}


async def test_unknown_kind_or_tier_is_rejected(client, paired, assets_root):
    alice, _bob = paired
    assets_root("reactions", "standard", "a.png")
    assert (await client.get("/api/v1/assets/gifs", headers=auth_headers(alice))).status_code == 422
    r = await client.get("/api/v1/assets/reactions/secret/a", headers=auth_headers(alice))
    assert r.status_code == 422


async def test_get_returns_png(client, paired, assets_root):
    alice, _bob = paired
    assets_root("stickers", "nsfw", "s-1.png")
    r = await client.get("/api/v1/assets/stickers/nsfw/s-1", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _PNG


async def test_get_returns_png_from_a_style_folder(client, paired, assets_root):
    alice, _bob = paired
    assets_root("stickers", "nsfw", "cartoon/s-1.png")
    r = await client.get("/api/v1/assets/stickers/nsfw/cartoon/s-1", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.content == _PNG


@pytest.mark.parametrize(
    "bad_id",
    [
        "missing",
        "..%2Fsecret",
        "cartoon/deeper/s-1",  # a second level is never valid
        "s-1.png",
        "S-1",
        "cartoon//s-1",
        "/s-1",
        "cartoon/",
    ],
)
async def test_get_rejects_unknown_or_malformed_ids(client, paired, assets_root, bad_id):
    alice, _bob = paired
    assets_root("stickers", "standard", "s-1.png")
    assets_root("stickers", "standard", "cartoon/s-1.png")
    assets_root("stickers", "standard", "cartoon/deeper/s-1.png")
    r = await client.get(f"/api/v1/assets/stickers/standard/{bad_id}", headers=auth_headers(alice))
    assert r.status_code == 404


async def test_get_does_not_cross_tiers(client, paired, assets_root):
    alice, _bob = paired
    assets_root("stickers", "nsfw", "cartoon/only-nsfw.png")
    r = await client.get("/api/v1/assets/stickers/standard/cartoon/only-nsfw", headers=auth_headers(alice))
    assert r.status_code == 404


async def test_symlinks_are_neither_listed_nor_served(client, paired, assets_root):
    alice, _bob = paired
    outside = assets_root.root / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(_PNG)
    tier_dir = assets_root.root / "stickers" / "standard"
    tier_dir.mkdir(parents=True)
    try:
        (tier_dir / "linked-file.png").symlink_to(outside / "secret.png")
        (tier_dir / "linked-dir").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    assets_root("stickers", "standard", "real.png")

    listing = await client.get("/api/v1/assets/stickers", headers=auth_headers(alice))
    assert listing.json()["standard"] == ["real"]
    for asset_id in ("linked-file", "linked-dir/secret"):
        r = await client.get(f"/api/v1/assets/stickers/standard/{asset_id}", headers=auth_headers(alice))
        assert r.status_code == 404


async def test_the_old_emoji_routes_are_gone(client, paired, assets_root):
    alice, _bob = paired
    assets_root("reactions", "nsfw", "nsfw-1.png")
    for path in ("/api/v1/emojis/nsfw", "/api/v1/emojis/nsfw/nsfw-1"):
        r = await client.get(path, headers=auth_headers(alice))
        assert r.status_code == 404


def test_is_valid_asset_id():
    valid = asset_pack_service.is_valid_asset_id
    assert valid("kiss") and valid("cartoon/kiss") and valid("3d/a-1_b")
    assert not valid("a/b/c")
    assert not valid("")
    assert not valid("a//b")
    assert not valid("../a")
    assert not valid("A/b")
    assert not valid("a/b.png")
    assert not valid("x" * 65)


def test_is_valid_reaction_effect(assets_root):
    assets_root("reactions", "nsfw", "n-1.png")
    assets_root("reactions", "nsfw", "cartoon/n-2.png")
    assets_root("reactions", "standard", "s-1.png")
    assets_root("stickers", "standard", "only-sticker.png")
    valid = asset_pack_service.is_valid_reaction_effect
    assert valid("nsfw:n-1")
    assert valid("nsfw:cartoon/n-2")
    assert valid("std:s-1")
    assert not valid("std:n-1")  # right file, wrong tier
    assert not valid("std:cartoon/n-2")
    assert not valid("nsfw:s-1")
    assert not valid("std:only-sticker")  # stickers are never reaction effects
    assert not valid("std:../x")
    assert not valid("nsfw:cartoon/deeper/n-2")
    assert not valid("s-1")
    assert not valid(None)
    assert not valid(["std:s-1"])


def test_list_ids_uses_kind_and_tier(assets_root):
    assets_root("reactions", "standard", "a.png")
    assert asset_pack_service.list_ids(AssetKind.REACTIONS, AssetTier.STANDARD) == ["a"]
    assert asset_pack_service.list_ids(AssetKind.REACTIONS, AssetTier.NSFW) == []
    assert asset_pack_service.list_ids(AssetKind.STICKERS, AssetTier.STANDARD) == []
