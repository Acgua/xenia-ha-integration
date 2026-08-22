"""Contract tests for the persistent shot store."""

from unittest.mock import patch

from homeassistant.helpers.storage import Store

from custom_components.xenia_home.const import XENIA_DOMAIN
from custom_components.xenia_home.shot_store import XeniaShotStore
from tests.fixtures.shots import shot_payload

ENTRY_ID = "test_entry"


async def _loaded_store(hass, entry_id: str = ENTRY_ID) -> XeniaShotStore:
    store = XeniaShotStore(hass, entry_id)
    await store.async_load()
    return store


async def test_added_shot_is_listed_and_retrievable(hass):
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    summaries = store.list_shots()
    assert summaries == [
        {
            "shot_id": payload["start_time"],
            "start_time": payload["start_time"],
            "brew_end_time": payload["brew_end_time"],
            "duration_seconds": payload["duration_seconds"],
            "final_weight_g": payload["weights"][-1],
        }
    ]
    shots = await store.async_get_shots([payload["start_time"]])
    assert shots == [{**payload, "shot_id": payload["start_time"]}]


async def test_list_is_newest_first_across_months(hass):
    store = await _loaded_store(hass)
    old = shot_payload("2026-06-15T08:00:00.000+00:00")
    new = shot_payload("2026-07-01T10:00:00.000+00:00")
    await store.async_add_shot(old)
    await store.async_add_shot(new)
    assert [s["shot_id"] for s in store.list_shots()] == [
        new["start_time"],
        old["start_time"],
    ]
    # chunking is invisible: both shots retrievable together, request order kept
    shots = await store.async_get_shots([old["start_time"], new["start_time"]])
    assert [s["shot_id"] for s in shots] == [old["start_time"], new["start_time"]]


async def test_history_survives_reload(hass):
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [payload["start_time"]]
    shots = await reloaded.async_get_shots([payload["start_time"]])
    assert shots[0]["weights"] == payload["weights"]


async def test_duplicate_add_is_ignored(hass):
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload())
    await store.async_add_shot(shot_payload())
    assert len(store.list_shots()) == 1


async def test_get_omits_unknown_ids(hass):
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)
    shots = await store.async_get_shots(
        ["2020-01-01T00:00:00.000+00:00", payload["start_time"], "../evil"]
    )
    assert [s["shot_id"] for s in shots] == [payload["start_time"]]


async def test_delete_removes_only_target_and_persists(hass):
    store = await _loaded_store(hass)
    keep = shot_payload("2026-07-01T10:00:00.000+00:00")
    drop = shot_payload("2026-07-02T10:00:00.000+00:00")
    await store.async_add_shot(keep)
    await store.async_add_shot(drop)

    assert await store.async_delete_shot(drop["start_time"]) is True
    assert await store.async_delete_shot(drop["start_time"]) is False

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [keep["start_time"]]


async def test_remove_deletes_everything(hass):
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload("2026-06-15T08:00:00.000+00:00"))
    await store.async_add_shot(shot_payload("2026-07-01T10:00:00.000+00:00"))
    await store.async_remove()

    reloaded = await _loaded_store(hass)
    assert reloaded.list_shots() == []


async def test_entries_are_isolated(hass):
    store_a = await _loaded_store(hass, "entry_a")
    store_b = await _loaded_store(hass, "entry_b")
    await store_a.async_add_shot(shot_payload())
    assert store_b.list_shots() == []


async def test_migrated_flag_persists(hass):
    store = await _loaded_store(hass)
    assert store.migrated is False
    await store.async_set_migrated()

    reloaded = await _loaded_store(hass)
    assert reloaded.migrated is True


async def test_corrupt_index_is_tolerated(hass):
    with patch.object(Store, "async_load", side_effect=OSError("corrupt")):
        store = await _loaded_store(hass)
    assert store.list_shots() == []

    payload = shot_payload()
    await store.async_add_shot(payload)
    assert [s["shot_id"] for s in store.list_shots()] == [payload["start_time"]]


async def test_corrupt_chunk_is_tolerated(hass):
    store = await _loaded_store(hass)
    payload = shot_payload()
    await store.async_add_shot(payload)

    reloaded = await _loaded_store(hass)
    with patch.object(Store, "async_load", side_effect=OSError("corrupt")):
        assert await reloaded.async_get_shots([payload["start_time"]]) == []

    # store remains usable after the corrupt read
    assert [s["shot_id"] for s in reloaded.list_shots()] == [payload["start_time"]]
    other = shot_payload("2026-08-01T10:00:00.000+00:00")
    await reloaded.async_add_shot(other)
    assert {s["shot_id"] for s in reloaded.list_shots()} == {
        payload["start_time"],
        other["start_time"],
    }


async def test_add_shot_with_unparseable_start_time_is_ignored(hass):
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload(start_time="not-a-timestamp"))
    assert store.list_shots() == []


async def test_delete_last_shot_of_month_removes_chunk_file(hass):
    store = await _loaded_store(hass)
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    await store.async_add_shot(june)
    await store.async_add_shot(july)

    assert await store.async_delete_shot(june["start_time"]) is True

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [july["start_time"]]
    shots = await reloaded.async_get_shots([july["start_time"], june["start_time"]])
    assert [s["shot_id"] for s in shots] == [july["start_time"]]


async def test_files_live_in_domain_folder(hass, hass_storage):
    store = await _loaded_store(hass)
    await store.async_add_shot(shot_payload())

    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-07" in hass_storage
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)


def _flat_storage_entry(key: str, data: dict) -> dict:
    return {"version": 1, "minor_version": 1, "key": key, "data": data}


def _seed_flat_layout(hass_storage, *payloads) -> None:
    """Write a v0.7.0-beta.1 flat file layout for the given shots."""
    shots = []
    chunks: dict[str, dict] = {}
    for payload in payloads:
        month = payload["start_time"][:7]
        chunks.setdefault(month, {})[payload["start_time"]] = payload
        shots.append(
            {
                "shot_id": payload["start_time"],
                "start_time": payload["start_time"],
                "brew_end_time": payload["brew_end_time"],
                "duration_seconds": payload["duration_seconds"],
                "final_weight_g": payload["weights"][-1],
                "month": month,
            }
        )
    index_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_index"
    hass_storage[index_key] = _flat_storage_entry(
        index_key, {"migrated": True, "shots": shots}
    )
    for month, chunk in chunks.items():
        chunk_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_{month}"
        hass_storage[chunk_key] = _flat_storage_entry(chunk_key, chunk)


async def test_flat_beta_layout_is_relocated(hass, hass_storage):
    june = shot_payload("2026-06-15T08:00:00.000+00:00")
    july = shot_payload("2026-07-01T10:00:00.000+00:00")
    _seed_flat_layout(hass_storage, june, july)

    store = await _loaded_store(hass)

    # history is intact and the recorder import will not run again
    assert [s["shot_id"] for s in store.list_shots()] == [
        july["start_time"],
        june["start_time"],
    ]
    shots = await store.async_get_shots([june["start_time"]])
    assert shots == [{**june, "shot_id": june["start_time"]}]
    assert store.migrated is True

    # flat files are gone, folder files exist
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-06" in hass_storage
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_2026-07" in hass_storage


async def test_relocation_runs_once(hass, hass_storage):
    payload = shot_payload()
    _seed_flat_layout(hass_storage, payload)
    await _loaded_store(hass)

    reloaded = await _loaded_store(hass)
    assert [s["shot_id"] for s in reloaded.list_shots()] == [payload["start_time"]]


async def test_relocation_rerun_keeps_moved_chunks(hass, hass_storage):
    """A crash between chunk move and index save must not lose payloads."""
    payload = shot_payload()
    _seed_flat_layout(hass_storage, payload)
    month = payload["start_time"][:7]
    flat_chunk_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_{month}"
    folder_chunk_key = f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_{month}"
    hass_storage[folder_chunk_key] = _flat_storage_entry(
        folder_chunk_key, hass_storage.pop(flat_chunk_key)["data"]
    )

    store = await _loaded_store(hass)

    shots = await store.async_get_shots([payload["start_time"]])
    assert shots == [{**payload, "shot_id": payload["start_time"]}]
    assert not any(k.startswith(f"{XENIA_DOMAIN}.") for k in hass_storage)


async def test_corrupt_flat_index_leaves_files_and_starts_empty(hass, hass_storage):
    payload = shot_payload()
    _seed_flat_layout(hass_storage, payload)
    flat_index_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_index"

    real_load = Store.async_load

    async def load(self):
        if self.key == flat_index_key:
            raise OSError("corrupt")
        return await real_load(self)

    with patch.object(Store, "async_load", load):
        store = await _loaded_store(hass)

    assert store.list_shots() == []
    # the unreadable flat files stay untouched for manual recovery
    assert flat_index_key in hass_storage

    # the store is usable and writes to the folder layout
    await store.async_add_shot(payload)
    assert [s["shot_id"] for s in store.list_shots()] == [payload["start_time"]]
    assert f"{XENIA_DOMAIN}/{ENTRY_ID}.shots_index" in hass_storage


async def test_malformed_flat_index_is_tolerated(hass, hass_storage):
    flat_index_key = f"{XENIA_DOMAIN}.{ENTRY_ID}.shots_index"
    hass_storage[flat_index_key] = _flat_storage_entry(flat_index_key, {"bogus": 1})

    store = await _loaded_store(hass)

    assert store.list_shots() == []
    assert flat_index_key in hass_storage
