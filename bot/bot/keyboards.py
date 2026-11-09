"""Reply and inline keyboards. Callback data formats (all far below Telegram's 64-byte limit):
m:<action>:<machine_id>   machine chosen for an action
                          (report | sound | photo | panel | baseline | refphoto | manual | go)
                          go = send the message that is waiting for a machine (submit.py)
role:<operator|master>    lang:<ru|kk>    type:<machine type>
add_machine  baseline  ref_photo  manual      master tools under "My machines"
panel_ok  panel_edit                          confirm / correct values read from a display
res:<incident_id>  esc:<incident_id>  pg:<incident_id>   card buttons
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.texts import t


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_report"))],
            [KeyboardButton(text=t(lang, "btn_sound")), KeyboardButton(text=t(lang, "btn_photo"))],
            [KeyboardButton(text=t(lang, "btn_panel")), KeyboardButton(text=t(lang, "btn_machines"))],
        ],
        resize_keyboard=True,
    )


def roles(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "role_operator"), callback_data="role:operator")],
            [InlineKeyboardButton(text=t(lang, "role_master"), callback_data="role:master")],
        ]
    )


def languages() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="Қазақша", callback_data="lang:kk"),
            ]
        ]
    )


def machines(items: list[dict], action: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=m["name"], callback_data=f"m:{action}:{m['id']}")] for m in items]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def master_tools(lang: str) -> InlineKeyboardMarkup:
    """Under "My machines" for masters/owners: add a machine, reference sound/photo, PDF manual."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_add_machine"), callback_data="add_machine")],
            [InlineKeyboardButton(text=t(lang, "btn_baseline"), callback_data="baseline")],
            [InlineKeyboardButton(text=t(lang, "btn_ref_photo"), callback_data="ref_photo")],
            [InlineKeyboardButton(text=t(lang, "btn_manual"), callback_data="manual")],
        ]
    )


def panel_confirm(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_confirm"), callback_data="panel_ok"),
                InlineKeyboardButton(text=t(lang, "btn_edit"), callback_data="panel_edit"),
            ]
        ]
    )


def machine_types(catalog: list[dict], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(lang == "kk" and item.get("title_kk")) or item["title_ru"],
                callback_data=f"type:{item['type']}",
            )
        ]
        for item in catalog
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card(incident: dict, lang: str = "ru") -> InlineKeyboardMarkup:
    """Buttons under an incident card; the manual button only when pages are cited."""
    incident_id = incident["id"]
    rows = [
        [
            InlineKeyboardButton(text=t(lang, "btn_resolved"), callback_data=f"res:{incident_id}"),
            InlineKeyboardButton(text=t(lang, "btn_call_master"), callback_data=f"esc:{incident_id}"),
        ]
    ]
    if incident.get("manual_pages"):
        rows.append(
            [InlineKeyboardButton(text=t(lang, "btn_manual_page"), callback_data=f"pg:{incident_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
