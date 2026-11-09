"""Static wiring check: everything the handlers reference exists, and every button has a handler.

Handlers only touch keyboards / API methods / texts when a user presses something, so a missing
function would crash only in Telegram. This test reads the source and checks the references.
"""

import re
from pathlib import Path

from bot import keyboards
from bot.api_client import FiboApi
from bot.states import Flow
from bot.texts import TEXTS

BOT_DIR = Path(__file__).resolve().parents[1] / "bot"
HANDLERS = "\n".join(p.read_text(encoding="utf-8") for p in sorted((BOT_DIR / "handlers").glob("*.py")))
ALL_CODE = (
    HANDLERS
    + (BOT_DIR / "delivery.py").read_text(encoding="utf-8")
    + (BOT_DIR / "keyboards.py").read_text(encoding="utf-8")
)


def test_keyboard_functions_exist():
    for name in set(re.findall(r"keyboards\.(\w+)\(", HANDLERS + (BOT_DIR / "delivery.py").read_text())):
        assert hasattr(keyboards, name), f"keyboards.{name} is used but not defined"


def test_api_methods_exist():
    for name in set(re.findall(r"\bapi\.(\w+)\(", HANDLERS)):
        assert hasattr(FiboApi, name), f"FiboApi.{name} is used but not defined"


def test_text_keys_exist():
    for key in set(re.findall(r"\bt\([^,()]+,\s*[\"'](\w+)[\"']", ALL_CODE)):
        assert key in TEXTS["ru"], f"text key {key!r} is used but missing"


def test_states_exist():
    for name in set(re.findall(r"Flow\.(\w+)", HANDLERS)):
        assert hasattr(Flow, name), f"Flow.{name} is used but not defined"


def test_every_button_has_a_handler():
    source = (BOT_DIR / "keyboards.py").read_text(encoding="utf-8")
    for literal in set(re.findall(r'callback_data="(\w+)"', source)):
        assert f'"{literal}"' in HANDLERS, f'button "{literal}" has no handler'
    for prefix in set(re.findall(r'callback_data=f"(\w+):', source)) | {"role", "lang"}:
        assert f'startswith("{prefix}:")' in HANDLERS, f'buttons "{prefix}:…" have no handler'


# Values that are numbers, or are escaped where they are built (see the handler code).
SAFE_TEXT_VALUES = {
    "count",
    "recommended",
    "pages",
    "page",
    "hours",
    "loss",  # numbers from the backend
    "items=items",
    "values=rejected",
    "values=format_values(values)",  # escaped while building the list
}


def test_dynamic_message_values_are_html_escaped():
    """parse_mode=HTML: a name like "Ali & Co" must be escaped, or Telegram rejects the message."""
    unsafe = []
    for path in sorted((BOT_DIR / "handlers").glob("*.py")) + [BOT_DIR / "delivery.py"]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for call in re.findall(r"\bt\([^()]*(?:\([^()]*(?:\([^()]*\))?[^()]*\)[^()]*)*\)", line):
                for name, value in re.findall(
                    r"(\w+)=([^,]+?(?:\([^()]*(?:\([^()]*\))?[^()]*\))?)(?=,|\)$)", call
                ):
                    value = value.strip()
                    if (
                        value.startswith("html.escape(")
                        or name in SAFE_TEXT_VALUES
                        or f"{name}={value}" in SAFE_TEXT_VALUES
                    ):
                        continue
                    unsafe.append(f"{path.name}:{number}: {name}={value}")
    assert not unsafe, unsafe
