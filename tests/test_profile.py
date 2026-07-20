from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, get_args

import pytest
from iterm2 import api_pb2, rpc

from iterm2_api_wrapper.api.it2profile import (
    DynamicProfile,
    PartialProfile,
    Profile,
    ProfileProperties,
    ProfilePropertyKey,
    process_dynamic_profiles_payload,
)


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2connection import Connection
    from iterm2_api_wrapper.api.it2profile import DynamicProfilesPayload


def _connection() -> Connection:
    return cast("Connection", object())


def _profiles_response(*profiles: dict[str, object]) -> api_pb2.ServerOriginatedMessage:
    response = api_pb2.ServerOriginatedMessage()

    for profile_properties in profiles:
        response_profile = response.list_profiles_response.profiles.add()
        for key, value in profile_properties.items():
            prop = response_profile.properties.add()
            prop.key = key
            prop.json_value = json.dumps(value)

    return response


def test_profile_async_get_returns_typed_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[tuple[list[str] | None, object]] = []

        async def fake_list_profiles(connection: Connection, guids: list[str] | None, properties: object):
            calls.append((guids, properties))
            return _profiles_response({"Guid": "GUID-1", "Name": "Default"})

        monkeypatch.setattr(rpc, "async_list_profiles", fake_list_profiles)

        profiles = await Profile.async_get(_connection(), ["GUID-1"])

        assert isinstance(profiles[0], Profile)
        assert profiles[0].guid == "GUID-1"
        assert profiles[0].name == "Default"
        assert calls == [(["GUID-1"], None)]

    asyncio.run(scenario())


def test_partial_profile_async_query_returns_typed_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[tuple[list[str] | None, object]] = []

        async def fake_list_profiles(connection: Connection, guids: list[str] | None, properties: object):
            calls.append((guids, properties))
            return _profiles_response({"Guid": "GUID-1", "Name": "Default"})

        monkeypatch.setattr(rpc, "async_list_profiles", fake_list_profiles)

        profiles = await PartialProfile.async_query(_connection())

        assert isinstance(profiles[0], PartialProfile)
        assert profiles[0].guid == "GUID-1"
        assert profiles[0].name == "Default"
        assert calls == [(None, ("Guid", "Name"))]

    asyncio.run(scenario())


def test_dynamic_profile_payload_omits_runtime_only_fields() -> None:
    properties: ProfileProperties = {"Load Shell Integration Automatically": 1}

    dynamic_profile = DynamicProfile(_connection(), "iterm2-api-test", properties=properties)
    payload_profile = dynamic_profile.payload["Profiles"][0]

    assert properties == {"Load Shell Integration Automatically": 1}
    assert payload_profile.get("Load Shell Integration Automatically") == 1
    assert payload_profile.get("Name") == "iterm2-api-test"
    assert payload_profile.get("Guid") == dynamic_profile.guid
    assert payload_profile.get("Rewritable") is True
    assert payload_profile.get("Dynamic Profile Parent Name") == "Default"
    assert "Dynamic Profile Filename" not in payload_profile
    assert "Is Dynamic Profile" not in payload_profile


def test_dynamic_profile_rejects_conflicting_parent_identifiers() -> None:
    dynamic_profile = cast(Any, DynamicProfile)

    with pytest.raises(ValueError, match="either parent_profile_guid or parent_profile_name"):
        dynamic_profile(
            _connection(),
            "iterm2-api-test",
            parent_profile_guid="GUID-1",
            parent_profile_name="Default",
        )


def test_dynamic_profile_async_create_polls_until_registered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def scenario() -> None:
        dynamic_profile = DynamicProfile(_connection(), "iterm2-api-test")
        calls: list[tuple[list[str] | None, object]] = []
        responses = [
            _profiles_response(),
            _profiles_response(),
            _profiles_response({"Guid": dynamic_profile.guid, "Name": "iterm2-api-test"}),
        ]
        sleep_calls: list[float] = []

        async def fake_list_profiles(connection: Connection, guids: list[str] | None, properties: object):
            calls.append((guids, properties))
            return responses.pop(0)

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        dynamic_profiles_directory = tmp_path / "DynamicProfiles"
        dynamic_profile_path = dynamic_profiles_directory / "iterm2-api-wrapper.json"
        monkeypatch.setattr(DynamicProfile, "DYNAMIC_PROFILES_DIRECTORY", dynamic_profiles_directory)
        monkeypatch.setattr(DynamicProfile, "DYNAMIC_PROFILE_PATH", dynamic_profile_path)
        monkeypatch.setattr(DynamicProfile, "STAGING_PATH", tmp_path / ".iterm2-api-wrapper.json.tmp")
        monkeypatch.setattr(rpc, "async_list_profiles", fake_list_profiles)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        profile = await dynamic_profile.async_create()

        assert isinstance(profile, Profile)
        assert profile.guid == dynamic_profile.guid
        assert calls == [([dynamic_profile.guid], None)] * 3
        assert sleep_calls == [DynamicProfile.PROFILE_LOAD_INITIAL_DELAY]
        assert dynamic_profile_path.exists()

    asyncio.run(scenario())


def test_dynamic_profile_async_create_returns_existing_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        dynamic_profile = DynamicProfile(
            _connection(),
            "iterm2-api-test",
        )
        calls: list[tuple[list[str] | None, object]] = []

        dynamic_profiles_directory = tmp_path / "DynamicProfiles"
        dynamic_profile_path = dynamic_profiles_directory / "iterm2-api-wrapper.json"
        staging_path = tmp_path / ".iterm2-api-wrapper.json.tmp"

        dynamic_profiles_directory.mkdir(parents=True)
        dynamic_profile_path.write_text(
            json.dumps(
                {
                    "Profiles": [
                        {
                            "Name": "iterm2-api-test",
                            "Guid": dynamic_profile.guid,
                            "Rewritable": True,
                            "Dynamic Profile Parent Name": "Default",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        async def fake_list_profiles(
            connection: Connection,
            guids: list[str] | None,
            properties: object,
        ):
            calls.append((guids, properties))
            return _profiles_response(
                {
                    "Guid": dynamic_profile.guid,
                    "Name": "iterm2-api-test",
                    "Is Dynamic Profile": 1,
                    "Dynamic Profile Filename": str(dynamic_profile_path),
                }
            )

        monkeypatch.setattr(
            DynamicProfile,
            "DYNAMIC_PROFILES_DIRECTORY",
            dynamic_profiles_directory,
        )
        monkeypatch.setattr(
            DynamicProfile,
            "DYNAMIC_PROFILE_PATH",
            dynamic_profile_path,
        )
        monkeypatch.setattr(
            DynamicProfile,
            "STAGING_PATH",
            staging_path,
        )
        monkeypatch.setattr(
            rpc,
            "async_list_profiles",
            fake_list_profiles,
        )

        profile = await dynamic_profile.async_create()

        assert isinstance(profile, Profile)
        assert profile.guid == dynamic_profile.guid

        # async_create existence query, async_update ownership query, and
        # convergence query.
        assert calls == [([dynamic_profile.guid], None)] * 3

    asyncio.run(scenario())


def test_dynamic_profile_async_update_removal_converges_to_parent_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        connection = _connection()
        dynamic_profile = DynamicProfile(
            connection,
            "iterm2-api-test",
            parent_profile_guid="PARENT-GUID",
        )

        dynamic_profiles_directory = tmp_path / "DynamicProfiles"
        dynamic_profile_path = dynamic_profiles_directory / "iterm2-api-wrapper.json"
        staging_path = tmp_path / ".iterm2-api-wrapper.json.tmp"

        dynamic_profiles_directory.mkdir(parents=True)
        dynamic_profile_path.write_text(
            json.dumps(
                {
                    "Profiles": [
                        {
                            "Name": "iterm2-api-test",
                            "Guid": dynamic_profile.guid,
                            "Rewritable": True,
                            "Dynamic Profile Parent GUID": "PARENT-GUID",
                            "Badge Text": "explicit-child-value",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        target_profile_queries = 0
        calls: list[tuple[list[str] | None, object]] = []

        async def fake_list_profiles(
            rpc_connection: Connection,
            guids: list[str] | None,
            properties: object,
        ):
            nonlocal target_profile_queries

            assert rpc_connection is connection
            calls.append((guids, properties))

            if guids == ["PARENT-GUID"]:
                return _profiles_response(
                    {
                        "Guid": "PARENT-GUID",
                        "Name": "Parent",
                        "Badge Text": "inherited-parent-value",
                    }
                )

            if guids == [dynamic_profile.guid]:
                target_profile_queries += 1

                if target_profile_queries == 1:
                    # The dynamic profile before iTerm2 reloads the updated
                    # definition.
                    return _profiles_response(
                        {
                            "Guid": dynamic_profile.guid,
                            "Name": "iterm2-api-test",
                            "Badge Text": "explicit-child-value",
                            "Is Dynamic Profile": 1,
                            "Dynamic Profile Filename": str(dynamic_profile_path),
                        }
                    )

                # After reload, the explicit key is absent from the JSON
                # definition, but the effective profile inherits the parent's
                # value.
                return _profiles_response(
                    {
                        "Guid": dynamic_profile.guid,
                        "Name": "iterm2-api-test",
                        "Badge Text": "inherited-parent-value",
                        "Is Dynamic Profile": 1,
                        "Dynamic Profile Filename": str(dynamic_profile_path),
                    }
                )

            raise AssertionError(f"Unexpected profile query: {guids!r}")

        monkeypatch.setattr(
            DynamicProfile,
            "DYNAMIC_PROFILES_DIRECTORY",
            dynamic_profiles_directory,
        )
        monkeypatch.setattr(
            DynamicProfile,
            "DYNAMIC_PROFILE_PATH",
            dynamic_profile_path,
        )
        monkeypatch.setattr(
            DynamicProfile,
            "STAGING_PATH",
            staging_path,
        )
        monkeypatch.setattr(
            rpc,
            "async_list_profiles",
            fake_list_profiles,
        )

        profile = await dynamic_profile.async_update(
            remove_properties=("Badge Text",),
        )

        assert profile.all_properties.get("Badge Text") == ("inherited-parent-value")

        persisted_payload = json.loads(dynamic_profile_path.read_text(encoding="utf-8"))
        persisted_definition = persisted_payload["Profiles"][0]

        assert "Badge Text" not in persisted_definition
        assert persisted_definition["Name"] == "iterm2-api-test"
        assert persisted_definition["Guid"] == dynamic_profile.guid
        assert persisted_definition["Rewritable"] is True
        assert persisted_definition["Dynamic Profile Parent GUID"] == ("PARENT-GUID")

        assert calls == [
            ([dynamic_profile.guid], None),
            (["PARENT-GUID"], None),
            ([dynamic_profile.guid], None),
        ]
        assert not staging_path.exists()

    asyncio.run(scenario())


def test_process_dynamic_profiles_payload_read_mode_does_not_write(
    tmp_path: Path,
) -> None:
    dynamic_profile_path = tmp_path / "DynamicProfiles" / "iterm2-api-wrapper.json"
    staging_path = tmp_path / ".iterm2-api-wrapper.json.tmp"
    dynamic_profile_path.parent.mkdir(parents=True)

    expected_payload = {
        "Profiles": [
            {
                "Name": "iterm2-api-test",
                "Guid": "GUID-1",
            }
        ]
    }
    original_json = json.dumps(expected_payload, indent=4) + "\n"
    dynamic_profile_path.write_text(
        original_json,
        encoding="utf-8",
    )

    payload = process_dynamic_profiles_payload(
        dynamic_profile_path,
        staging_path,
    )

    assert payload == expected_payload
    assert dynamic_profile_path.read_text(encoding="utf-8") == original_json
    assert not staging_path.exists()


def test_process_dynamic_profiles_payload_atomically_publishes_payload(
    tmp_path: Path,
) -> None:
    dynamic_profile_path = tmp_path / "DynamicProfiles" / "iterm2-api-wrapper.json"
    staging_path = tmp_path / ".iterm2-api-wrapper.json.tmp"

    payload: DynamicProfilesPayload = {
        "Profiles": [
            {
                "Name": "iterm2-api-test",
                "Guid": "GUID-1",
                "Rewritable": True,
            }
        ]
    }

    result = process_dynamic_profiles_payload(
        dynamic_profile_path,
        staging_path,
        payload=payload,
    )

    assert result == payload
    assert json.loads(dynamic_profile_path.read_text(encoding="utf-8")) == payload
    assert not staging_path.exists()


def test_profile_property_key_covers_every_profile_property() -> None:
    assert set(get_args(ProfilePropertyKey)) == set(ProfileProperties.__annotations__)
