from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from iterm2 import api_pb2, rpc

from iterm2_api_wrapper.api.it2profile import DynamicProfile, PartialProfile, Profile, ProfileProperties


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2connection import Connection


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


def test_dynamic_profile_async_create_polls_until_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_dynamic_profile_async_create_returns_existing_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        dynamic_profile = DynamicProfile(_connection(), "iterm2-api-test")
        calls: list[tuple[list[str] | None, object]] = []

        async def fake_list_profiles(connection: Connection, guids: list[str] | None, properties: object):
            calls.append((guids, properties))
            return _profiles_response({"Guid": dynamic_profile.guid, "Name": "iterm2-api-test"})

        monkeypatch.setattr(rpc, "async_list_profiles", fake_list_profiles)

        profile = await dynamic_profile.async_create()

        assert isinstance(profile, Profile)
        assert profile.guid == dynamic_profile.guid
        assert calls == [([dynamic_profile.guid], None)]

    asyncio.run(scenario())
