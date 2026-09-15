from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from iterm2_api_wrapper._gen.gen_mainmenu import gen_menu_items_impl, main


def test_gen_menu_items_skips_entries_without_public_identifiers() -> None:
    items = ET.fromstring(
        """
        <items>
            <menuItem title="Selectable" identifier="Selectable.ID" />
            <menuItem title="Services">
                <menu key="submenu" systemMenu="services" />
            </menuItem>
            <menuItem title="Selector-backed">
                <connections>
                    <action selector="performAction:" target="-1" />
                </connections>
            </menuItem>
            <menuItem title="Disabled placeholder" enabled="NO" />
        </items>
        """
    )

    generated = gen_menu_items_impl(items)

    assert 'SELECTABLE = MenuItemIdentifier("Selectable", "Selectable.ID")' in generated
    assert "Services" not in generated
    assert "Selectorbacked" not in generated
    assert "Disabledplaceholder" not in generated


def test_main_emits_compilable_module(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    generated = capsys.readouterr().out

    compile(generated, "<generated-mainmenu>", "exec")
