"""FSM states (aiogram finite-state machine): where a user is in a multi-step dialogue."""

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    invite_code = State()
    role = State()
    language = State()


class Flow(StatesGroup):
    awaiting_machine_sound = State()  # next voice message is a machine-sound recording
    awaiting_baseline = State()  # next voice messages are reference (healthy) recordings
    awaiting_photo = State()  # next photo is a tool/part photo -> incident
    awaiting_panel = State()  # next photo is a controller display -> suggested readings
    awaiting_panel_edit = State()  # next text corrects the suggested readings
    awaiting_reference_photo = State()  # next photo is the machine's reference photo
    awaiting_manual = State()  # next document is the machine's PDF manual


class AddMachine(StatesGroup):
    machine_type = State()
    name = State()
