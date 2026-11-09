"""Fixed content of the demo data used by app/db/seed.py (synthetic, labelled is_demo=True).

Kept separate from the seeding logic so the data is easy to read and edit on its own.
"""

# name, type, model, criticality, cost per hour (KZT), avg repair h, maintenance interval h,
# days since last maintenance
METAL_MACHINES = [
    ("ЧПУ-1 фрезерный", "cnc_mill", "Haas VF-2", 3, "25000", 6.0, 500, 41),
    ("ЧПУ-2 фрезерный", "cnc_mill", "DMG Mori CMX 600", 3, "22000", 6.0, 500, 12),
    ("Токарный-1", "lathe", "16К20", 2, "12000", 4.0, 700, 25),
    ("Токарный-2", "lathe", "1К62", 2, "10000", 4.0, 700, 60),
    ("Ленточная пила", "band_saw", "Pilous ARG 250", 1, "4000", 2.0, 400, 10),
    ("Компрессор", "compressor", "Remeza СБ4", 2, "8000", 3.0, 1000, 90),
]
BAKERY_MACHINES = [
    ("Тестомес", "dough_mixer", "Л4-ХТВ", 3, "18000", 3.0, 300, 35),
    ("Подовая печь", "deck_oven", "Восход ХПЭ-750", 3, "20000", 5.0, 500, 15),
    ("Расстоечный шкаф", "proofer", "ШРЭ-2.1", 2, "6000", 2.0, 600, 50),
]
BAKERY_BATCH_VALUE_KZT = "45000"

# Hours since the last tool change (tool wear for the AI4I model). ЧПУ-1 and Токарный-2 run on a
# worn tool; the others had the tool replaced after their latest reading.
TOOL_CHANGED_HOURS_AGO = {"ЧПУ-1 фрезерный": 72, "ЧПУ-2 фрезерный": 6, "Токарный-1": 6, "Токарный-2": 100}

# Machines whose load/temperature (or humidity) drift upwards in the last week: the "risky" ones.
DRIFTING_MACHINES = {"ЧПУ-1 фрезерный", "Тестомес"}

# Typical temperature of food equipment, °C (anything else: 28).
FOOD_TEMPERATURE_C = {"deck_oven": 230, "proofer": 38}

# hours_to_fix = None -> still open; a number -> resolved that many hours after it was reported.
DEMO_INCIDENTS = [
    dict(
        machine="ЧПУ-1 фрезерный",
        user="operator",
        days_ago=1.5,
        input_type="voice",
        level="warning",
        transcript="Шпиндель гудит на высоких оборотах, раньше так не было",
        verdict="Вероятен износ подшипников шпинделя",
        causes=["износ подшипников шпинделя", "недостаток смазки"],
    ),
    dict(
        machine="Токарный-1",
        user="operator",
        days_ago=12,
        input_type="voice",
        level="critical",
        transcript="Патрон заклинило, деталь не снять",
        verdict="Заклинивание патрона",
        causes=["загрязнение кулачков патрона"],
        hours_to_fix=5.5,
    ),
    dict(
        machine="Компрессор",
        user="master",
        days_ago=20,
        input_type="audio",
        level="warning",
        verdict="Посторонний стук в компрессоре",
        causes=["износ клапанов"],
        hours_to_fix=2.0,
    ),
    dict(
        machine="ЧПУ-2 фрезерный",
        user="operator",
        days_ago=25,
        input_type="voice",
        level="critical",
        transcript="Из электрощита искры и запах гари",
        verdict="Остановка: искрение в электрощите",
        causes=["ослабленный контакт в электрощите"],
        hours_to_fix=8.0,
        safety=True,
    ),
    dict(
        machine="Ленточная пила",
        user="operator",
        days_ago=0.5,
        input_type="photo",
        level="normal",
        verdict="Видимых дефектов ленты не обнаружено",
        causes=[],
    ),
    dict(
        machine="Тестомес",
        user="baker",
        days_ago=3,
        input_type="voice",
        level="warning",
        transcript="Тестомес қатты дірілдейді",
        verdict="Повышенная вибрация тестомеса",
        causes=["износ ремня привода", "ослабление крепления"],
    ),
]
