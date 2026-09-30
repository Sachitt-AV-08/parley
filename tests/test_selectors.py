"""Selector inventory tests: verify DOM fallback selectors exist in recorded fixture HTML.

This test catches "selector rot" when WhatsApp changes their DOM structure.
It extracts CSS selectors from parley's source and verifies each one's
key components (IDs, classes, data-testid, roles) appear in the fixture HTML.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "whatsapp_dom.html"

# Extracted from src/parley/store/script.py and src/parley/backends/webview.py
# Each entry: (selector_string, description)
SELECTORS = [
    # From store/script.py DOM_CHATS_JS
    ('#pane-side [role="row"], [data-testid="chat-list"] [role="listitem"]', "chat list rows"),
    ('canvas[aria-label*="QR"], [data-testid="qr-code"]', "QR code elements"),
    ('#pane-side', "chat list pane"),
    ('[data-testid="chat-list"]', "chat list container"),
    # From backends/webview.py
    ('#pane-side input[role="textbox"]', "chat list search input"),
    ('div[data-testid="chat-list-search-container"] input', "search container input"),
    ('div[data-testid="chat-list-search-container"]', "search container"),
    ('input[role="textbox"][aria-label*="Search" i]', "search input by label"),
    ('input[data-testid="chat-list-search-input"]', "search input by testid"),
    ('div[data-testid="conversation-compose-box-input"]', "compose box"),
    ('#main header, header[data-testid="conversation-header"]', "conversation header"),
    ('span[dir="auto"], div[data-testid="conversation-title"]', "conversation title"),
    ('#pane-side [role="row"], #pane-side [role="button"]', "chat list items (webview)"),
    (
        '#main [data-pre-plain-text], '
        '#main [data-testid="conversation-panel-messages"] .copyable-text',
        "message bubbles",
    ),
]


def _load_fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _extract_components(selector: str) -> list[str]:
    """Extract identifiable components from a CSS selector.

    Returns a list of IDs, classes, data-testid, roles, and other
    attributes that must exist in the HTML for the selector to match.
    """
    components = []

    # IDs: #foo
    components.extend(re.findall(r'#([\w-]+)', selector))

    # Classes: .foo
    components.extend(re.findall(r'\.([\w-]+)', selector))

    # data-testid="foo"
    components.extend(re.findall(r'data-testid="([^"]+)"', selector))

    # role="foo"
    components.extend(re.findall(r'role="([^"]+)"', selector))

    # aria-label*="foo" (attribute contains) - capture the value
    components.extend(re.findall(r'aria-label\*="([^"]+)"', selector))

    # dir="auto"
    if 'dir="auto"' in selector:
        components.append('dir="auto"')

    # Attributes in brackets like [data-pre-plain-text] - only named attrs
    for m in re.finditer(r'\[([a-zA-Z][\w-]*)(?:="[^"]*")?\]', selector):
        attr = m.group(1)
        if attr.startswith("data-") or attr.startswith("aria-") or attr == "role":
            components.append(attr)

    return components


def _component_in_html(component: str, html: str) -> bool:
    """Check if a component exists in the HTML."""
    if component.startswith("#"):
        # ID: #foo -> id="foo"
        return f'id="{component[1:]}"' in html
    elif component.startswith("."):
        # Class: .foo -> class="... foo ..."
        return 'class="' in html and component[1:] in html
    elif component.startswith("data-testid="):
        # data-testid="foo" -> data-testid="foo"
        return component in html
    elif component.startswith("role="):
        # role="foo" -> role="foo"
        return component in html
    elif component.startswith("aria-label*="):
        # aria-label*="foo" -> aria-label="...foo..."
        val = component.split("=")[1].strip('"')
        return 'aria-label="' in html and val in html
    elif component.startswith("dir="):
        return component in html
    elif component.startswith("data-") or component.startswith("aria-") or component == "role":
        # Attribute presence
        return f'{component}="' in html
    else:
        # Fallback: check as substring
        return component in html


def test_fixture_exists():
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"


def test_selector_components_in_fixture():
    """Verify every selector's components exist in the fixture HTML."""
    html = _load_fixture()
    missing = []

    for selector, desc in SELECTORS:
        components = _extract_components(selector)
        for comp in components:
            if not _component_in_html(comp, html):
                missing.append((selector, desc, comp))

    if missing:
        msg = "Missing selector components in fixture:\n"
        for selector, desc, comp in missing:
            msg += f"  - {desc}: selector={selector!r} missing {comp!r}\n"
        pytest.fail(msg, pytrace=False)
