# QQ Group Chatbot Phase 4 Sticker Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stickers, QQ faces, and image memes selectable first-class reply parts for the platform-neutral social agent core.

**Architecture:** Reuse `SocialMessagePart`, `SocialReplyAction`, `SocialTarget`, and `StickerPreferences` as the existing module agreements for media-bearing replies. Add a small media reference model for stable IDs and a sticker library that can filter by emotion, scene, pack, role-card preferences, group allow/block lists, and send policy.

**Tech Stack:** Python 3.13, pytest, dataclasses, stdlib JSON fixtures.

---

## Reuse Audit

- Reuse `SocialMessagePart(kind="sticker", media_ref=...)` for outbound sticker parts.
- Reuse `SocialMessagePart(kind="image", media_ref=...)` for image memes.
- Reuse `SocialMessagePart(kind="qq_face", platform_data=...)` for native QQ face IDs.
- Reuse `SocialReplyAction` and `SocialTarget` to produce sendable reply actions.
- Reuse `CharacterCard.stickers` preferences for favorite packs, preferred style tags, emotion mapping, use frequency, sticker-only permission, and avoided tags.
- Do not add QQ SDK dependencies in this phase; adapters come later.
- Do not add YAML parsing in this phase; the project currently has no PyYAML runtime dependency, so fixtures use JSON.

## File Structure

- Create `src/isotope/features/social/media_refs.py`: media reference model and helpers.
- Create `src/isotope/features/social/stickers.py`: sticker library entries, selection request, selection result, reply action builder.
- Modify `src/isotope/features/social/__init__.py`: export Phase 4 names.
- Create `tests/unit/features/social/test_stickers.py`: sticker selection, policy, and reply action tests.
- Create `tests/fixtures/social/stickers/engineering.json`: valid sticker library fixture.

## Task 1: Sticker Library Selection

**Files:**
- Create: `src/isotope/features/social/media_refs.py`
- Create: `src/isotope/features/social/stickers.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_stickers.py`
- Create: `tests/fixtures/social/stickers/engineering.json`

- [ ] **Step 1: Write failing sticker selection tests**

Create `tests/unit/features/social/test_stickers.py` with tests for:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from isotope.features.social import (
    CharacterCard,
    MediaRef,
    SocialTarget,
    StickerLibrary,
    StickerLibraryEntry,
    StickerSelectionRequest,
)
from tests.unit.features.social.test_character_card import _card_dict


def _card() -> CharacterCard:
    data = _card_dict()
    data["stickers"]["style_tags"] = ["review", "helpful"]
    data["stickers"]["emotion_map"]["positive"] = ["ship"]
    return CharacterCard.from_dict(data)


def _library() -> StickerLibrary:
    return StickerLibrary(
        entries=(
            StickerLibraryEntry(
                sticker_id="ship-it",
                pack_id="engineering",
                media=MediaRef(
                    media_ref="qq-image://ship-it",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("ship", "review", "cheer"),
                meaning="代码通过时的轻松回应",
                allowed_groups=("12345",),
                source="engineering_pack",
            ),
            StickerLibraryEntry(
                sticker_id="calm-down",
                pack_id="engineering",
                media=MediaRef(
                    media_ref="qq-image://calm-down",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("calm", "review"),
                meaning="提醒先别急，按步骤排查",
                blocked_groups=("12345",),
                source="engineering_pack",
            ),
            StickerLibraryEntry(
                sticker_id="coffee",
                pack_id="casual",
                media=MediaRef(
                    media_ref="qq-image://coffee",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("coffee", "casual"),
                meaning="闲聊时的咖啡表情",
                source="casual_pack",
            ),
        )
    )


def test_sticker_library_selects_by_emotion_scene_and_role_preferences() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
        )
    )

    assert selected is not None
    assert selected.entry.sticker_id == "ship-it"
    assert selected.reasons == (
        "emotion_tag:ship",
        "scene_tag:review",
        "favorite_pack:engineering",
        "style_tag:review",
    )


def test_sticker_library_rejects_blocked_group() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="calm",
            scene_tags=("calm",),
            character_stickers=_card().stickers,
        )
    )

    assert selected is None


def test_sticker_library_can_load_json_fixture() -> None:
    payload = json.loads(
        Path("tests/fixtures/social/stickers/engineering.json").read_text(
            encoding="utf-8"
        )
    )

    library = StickerLibrary.from_dict(payload)

    assert library.entries[0].sticker_id == "ship-it"
    assert library.entries[0].media.media_ref == "qq-image://ship-it"


def test_sticker_only_reply_action_is_valid_when_allowed() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
            allow_sticker_only=True,
        )
    )
    assert selected is not None

    action = selected.to_reply_action(
        action_id="reply_sticker",
        target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
    )

    assert action.parts[0].kind == "sticker"
    assert action.parts[0].media_ref == "qq-image://ship-it"


def test_sticker_only_reply_requires_role_and_request_permission() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
            allow_sticker_only=False,
        )
    )
    assert selected is not None

    with pytest.raises(ValueError, match="sticker-only replies are not allowed"):
        selected.to_reply_action(
            action_id="reply_sticker",
            target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_stickers.py -q
```

Expected: FAIL because `MediaRef`, `StickerLibrary`, `StickerLibraryEntry`, and `StickerSelectionRequest` do not exist.

- [ ] **Step 3: Implement media refs and sticker library**

Create `src/isotope/features/social/media_refs.py` with:

- `MediaRef(media_ref, kind, source, checksum=None, local_path=None, platform_data={})`
- supported media kinds: `sticker`, `image`, `qq_face`, `file`, `voice`, `video`
- validation for non-empty IDs and dict-shaped platform data
- `from_dict()` and `to_public_dict()`

Create `src/isotope/features/social/stickers.py` with:

- `StickerLibraryEntry`
- `StickerSelectionRequest`
- `StickerSelectionResult`
- `StickerLibrary`
- filtering by enabled sticker policy, group allow/block lists, pack preference, avoided tags, emotion map tags, scene tags, and style tags
- emotion or scene tags must match before pack/style preferences can rank a sticker, so the bot does not send a random favorite-pack sticker for an unrelated moment
- deterministic selection by score desc, then `sticker_id`
- `StickerSelectionResult.to_reply_action(...)` that returns a `SocialReplyAction` with one `SocialMessagePart(kind="sticker")`

Export the new names from `src/isotope/features/social/__init__.py`.

- [ ] **Step 4: Add sticker fixture**

Create `tests/fixtures/social/stickers/engineering.json`:

```json
{
  "entries": [
    {
      "sticker_id": "ship-it",
      "pack_id": "engineering",
      "media": {
        "media_ref": "qq-image://ship-it",
        "kind": "sticker",
        "source": "local_pack"
      },
      "tags": ["ship", "review", "cheer"],
      "meaning": "代码通过时的轻松回应",
      "allowed_groups": ["12345"],
      "source": "engineering_pack"
    }
  ]
}
```

- [ ] **Step 5: Run sticker tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_stickers.py -q
```

Expected: PASS.

## Task 2: Regression And Product Acceptance

**Files:**
- Modify: `docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-4-sticker-media.md`

- [ ] **Step 1: Run full social regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all social tests pass.

- [ ] **Step 2: Run shared supervisor regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected supervisor tests pass.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Product checklist**

Confirm from tests and code:

- sticker choice is connected to role-card pack/style/emotion settings;
- a blocked group cannot receive a blocked sticker;
- sticker-only reply actions are valid only when the request allows them;
- outbound stickers reuse the same `SocialReplyAction` path as text replies.

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-4-sticker-media.md src/isotope/features/social tests/unit/features/social/test_stickers.py tests/fixtures/social/stickers/engineering.json
git commit -m "feat(social): add sticker media library"
```
