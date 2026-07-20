#!/usr/bin/env python3

"""Live smoke test for wrapper-managed dynamic-profile updates.

This script:

1. Captures the existing wrapper-managed DynamicProfiles payload.
2. Creates a uniquely named dynamic profile inheriting from the default profile.
3. Confirms the explicit test property is persisted and exposed by iTerm2.
4. Updates the property through Profile.async_update().
5. Confirms both the JSON definition and runtime profile expose the update.
6. Removes the explicit property.
7. Confirms the JSON key is removed and the runtime profile inherits the
   default profile's effective value.
8. Confirms unrelated profile definitions and ordering remain unchanged.
9. Removes only the smoke profile during cleanup.

Requirements:

- iTerm2 must be running.
- The iTerm2 Python API must be enabled.
- Run this from the repository root.

Quick Run:

```
IT2_PYTEST_INTEGRATION=1 \
UV_CACHE_DIR=/private/tmp/iterm2-api-wrapper-uv-cache \
uv run --active --python=3.10 --group dev \
python scripts/smoke_dynamic_profile_update.py
```
"""

from __future__ import annotations

import asyncio
from typing import Any

from iterm2_api_wrapper.api.it2connection import (
    Connection,
    run_until_complete,
)
from iterm2_api_wrapper.api.it2profile import (
    DynamicProfile,
    DynamicProfileDefinition,
    DynamicProfilesPayload,
    Profile,
    ProfilePropertiesNoIdentifiers,
    process_dynamic_profiles_payload,
)


SMOKE_PROFILE_NAME = "iterm2-api-wrapper-dynamic-update-smoke"
SMOKE_PROPERTY = "Badge Text"
INITIAL_BADGE = "it2-wrapper-smoke-created"
UPDATED_BADGE = "it2-wrapper-smoke-updated"


def _read_wrapper_payload() -> DynamicProfilesPayload:
    """Return the current payload, or an empty payload if none exists."""
    if not DynamicProfile.DYNAMIC_PROFILE_PATH.exists():
        return {"Profiles": []}

    return process_dynamic_profiles_payload(
        DynamicProfile.DYNAMIC_PROFILE_PATH,
        DynamicProfile.STAGING_PATH,
    )


def _definition_for_guid(
    payload: DynamicProfilesPayload,
    guid: str,
) -> DynamicProfileDefinition:
    """Return one persisted definition or raise a useful assertion."""
    matches = [definition for definition in payload["Profiles"] if definition["Guid"] == guid]

    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one persisted definition for GUID {guid}, found {len(matches)}.")

    return matches[0]


def _profiles_without_guid(
    payload: DynamicProfilesPayload,
    guid: str,
) -> list[DynamicProfileDefinition]:
    """Return all definitions except the smoke-test definition."""
    return [definition for definition in payload["Profiles"] if definition["Guid"] != guid]


def _assert_unrelated_profiles_unchanged(
    *,
    original_profiles: list[DynamicProfileDefinition],
    current_payload: DynamicProfilesPayload,
    smoke_guid: str,
    stage: str,
) -> None:
    """Prove that the operation preserved unrelated data and ordering."""
    current_unrelated_profiles = _profiles_without_guid(
        current_payload,
        smoke_guid,
    )

    if current_unrelated_profiles != original_profiles:
        raise AssertionError(
            f"Unrelated dynamic profiles changed during {stage}.\n"
            f"Before: {original_profiles!r}\n"
            f"After:  {current_unrelated_profiles!r}"
        )


async def _wait_until_profile_is_absent(
    connection: Connection,
    guid: str,
) -> None:
    """Wait until iTerm2 removes the cleaned-up smoke profile."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DynamicProfile.PROFILE_LOAD_TIMEOUT
    delay = DynamicProfile.PROFILE_LOAD_INITIAL_DELAY

    while True:
        profiles = await Profile.async_get(
            connection,
            [guid],
        )
        if not profiles:
            return

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(
                f"iTerm2 did not remove smoke profile GUID {guid} within "
                f"{DynamicProfile.PROFILE_LOAD_TIMEOUT:.1f} seconds."
            )

        await asyncio.sleep(min(delay, remaining))
        delay = min(
            delay * 2,
            DynamicProfile.PROFILE_LOAD_MAX_DELAY,
        )


async def smoke_dynamic_profile_update(
    connection: Connection,
) -> None:
    """Execute the complete create, update, inherit, and cleanup smoke test."""
    wrapper_file_existed = DynamicProfile.DYNAMIC_PROFILE_PATH.exists()
    original_payload = _read_wrapper_payload()
    original_profiles = list(original_payload["Profiles"])

    parent_profile = await Profile.async_get_default(connection)
    parent_properties = parent_profile.all_properties

    initial_properties: ProfilePropertiesNoIdentifiers = {
        "Badge Text": INITIAL_BADGE,
    }
    updated_properties: ProfilePropertiesNoIdentifiers = {
        "Badge Text": UPDATED_BADGE,
    }

    dynamic_profile = DynamicProfile(
        connection,
        SMOKE_PROFILE_NAME,
        parent_profile_guid=parent_profile.guid,
        properties=initial_properties,
    )
    smoke_guid = dynamic_profile.guid

    if any(definition["Guid"] == smoke_guid for definition in original_profiles):
        raise RuntimeError(
            f"The smoke profile already exists in "
            f"'{DynamicProfile.DYNAMIC_PROFILE_PATH}'. Remove the existing "
            f"'{SMOKE_PROFILE_NAME}' definition before rerunning this script."
        )

    print(f"Wrapper payload: {DynamicProfile.DYNAMIC_PROFILE_PATH}")
    print(f"Parent profile:  {parent_profile.name} ({parent_profile.guid})")
    print(f"Smoke profile:   {SMOKE_PROFILE_NAME} ({smoke_guid})")

    try:
        print("\n[1/6] Creating dynamic profile...")
        created_profile = await dynamic_profile.async_create()

        assert created_profile.guid == smoke_guid
        assert created_profile.all_properties.get(SMOKE_PROPERTY) == (INITIAL_BADGE)

        created_payload = _read_wrapper_payload()
        created_definition = _definition_for_guid(
            created_payload,
            smoke_guid,
        )

        assert created_definition.get(SMOKE_PROPERTY) == INITIAL_BADGE
        assert created_definition["Name"] == SMOKE_PROFILE_NAME
        assert created_definition["Guid"] == smoke_guid
        assert created_definition.get("Rewritable") is True
        assert created_definition.get("Dynamic Profile Parent GUID") == (parent_profile.guid)
        assert "Dynamic Profile Filename" not in created_definition
        assert "Is Dynamic Profile" not in created_definition

        _assert_unrelated_profiles_unchanged(
            original_profiles=original_profiles,
            current_payload=created_payload,
            smoke_guid=smoke_guid,
            stage="creation",
        )
        print("      PASS: create persisted and registered correctly")

        print("\n[2/6] Updating explicit property...")
        updated_profile = await Profile.async_update(
            connection,
            SMOKE_PROFILE_NAME,
            properties=updated_properties,
        )

        assert updated_profile.guid == smoke_guid
        assert updated_profile.all_properties.get(SMOKE_PROPERTY) == (UPDATED_BADGE)

        updated_payload = _read_wrapper_payload()
        updated_definition = _definition_for_guid(
            updated_payload,
            smoke_guid,
        )

        assert updated_definition.get(SMOKE_PROPERTY) == UPDATED_BADGE

        _assert_unrelated_profiles_unchanged(
            original_profiles=original_profiles,
            current_payload=updated_payload,
            smoke_guid=smoke_guid,
            stage="explicit update",
        )
        print("      PASS: explicit update converged")

        print("\n[3/6] Removing explicit property...")
        inherited_profile = await Profile.async_update(
            connection,
            SMOKE_PROFILE_NAME,
            remove_properties=("Badge Text",),
        )

        removed_payload = _read_wrapper_payload()
        removed_definition = _definition_for_guid(
            removed_payload,
            smoke_guid,
        )

        assert SMOKE_PROPERTY not in removed_definition

        missing = object()
        expected_inherited_value: Any = parent_properties.get(
            SMOKE_PROPERTY,
            missing,
        )
        actual_inherited_value: Any = inherited_profile.all_properties.get(
            SMOKE_PROPERTY,
            missing,
        )

        assert actual_inherited_value == expected_inherited_value, (
            "The runtime dynamic profile did not converge to its parent's "
            f"{SMOKE_PROPERTY!r} value. "
            f"Expected {expected_inherited_value!r}; "
            f"received {actual_inherited_value!r}."
        )

        _assert_unrelated_profiles_unchanged(
            original_profiles=original_profiles,
            current_payload=removed_payload,
            smoke_guid=smoke_guid,
            stage="property removal",
        )

        if expected_inherited_value is missing:
            print("      PASS: property was removed from JSON and is absent from both parent and runtime profile")
        else:
            print(
                "      PASS: property was removed from JSON and inherited "
                f"the parent value {expected_inherited_value!r}"
            )

        print("\n[4/6] Verifying protected fields and metadata...")
        assert removed_definition["Name"] == SMOKE_PROFILE_NAME
        assert removed_definition["Guid"] == smoke_guid
        assert removed_definition.get("Rewritable") is True
        assert removed_definition.get("Dynamic Profile Parent GUID") == (parent_profile.guid)
        assert "Dynamic Profile Filename" not in removed_definition
        assert "Is Dynamic Profile" not in removed_definition
        print("      PASS: identity, parent, and payload hygiene preserved")

        print("\n[5/6] Verifying unrelated definitions and ordering...")
        final_test_payload = _read_wrapper_payload()
        _assert_unrelated_profiles_unchanged(
            original_profiles=original_profiles,
            current_payload=final_test_payload,
            smoke_guid=smoke_guid,
            stage="final verification",
        )
        print(f"      PASS: preserved {len(original_profiles)} unrelated profile definition(s) in their original order")

        print("\n[6/6] Functional smoke checks complete")
        print("      PASS: create, update, remove, inherit, and preserve")

    finally:
        print("\n[cleanup] Removing only the smoke profile...")

        if DynamicProfile.DYNAMIC_PROFILE_PATH.exists():
            current_payload = _read_wrapper_payload()
            remaining_profiles = _profiles_without_guid(
                current_payload,
                smoke_guid,
            )

            if len(remaining_profiles) != len(current_payload["Profiles"]):
                cleanup_payload: DynamicProfilesPayload = {
                    "Profiles": remaining_profiles,
                }
                process_dynamic_profiles_payload(
                    DynamicProfile.DYNAMIC_PROFILE_PATH,
                    DynamicProfile.STAGING_PATH,
                    payload=cleanup_payload,
                )
                await _wait_until_profile_is_absent(
                    connection,
                    smoke_guid,
                )

            # If the wrapper file did not exist before this smoke test and no
            # unrelated definitions appeared while it was running, remove the
            # now-empty file created solely by this script.
            if not wrapper_file_existed:
                cleaned_payload = _read_wrapper_payload()
                if not cleaned_payload["Profiles"]:
                    DynamicProfile.DYNAMIC_PROFILE_PATH.unlink()

        print("          PASS: smoke profile cleanup complete")


if __name__ == "__main__":
    run_until_complete(
        smoke_dynamic_profile_update,
        retry=True,
        debug=False,
    )
