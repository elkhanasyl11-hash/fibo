// Model feature names -> people's words. The backend already sends title_ru; this map covers Kazakh
// and any feature that arrives without a title. Unknown features are shown as they come.
const FEATURES: Record<string, { ru: string; kk: string }> = {
  tool_wear: { ru: "Износ инструмента", kk: "Құрал тозуы" },
  tool_wear_min: { ru: "Износ инструмента", kk: "Құрал тозуы" },
  torque: { ru: "Нагрузка шпинделя (момент)", kk: "Шпиндель жүктемесі (момент)" },
  torque_nm: { ru: "Нагрузка шпинделя (момент)", kk: "Шпиндель жүктемесі (момент)" },
  rotational_speed: { ru: "Обороты шпинделя", kk: "Шпиндель айналымы" },
  rotational_speed_rpm: { ru: "Обороты шпинделя", kk: "Шпиндель айналымы" },
  air_temperature: { ru: "Температура воздуха", kk: "Ауа температурасы" },
  air_temperature_k: { ru: "Температура воздуха", kk: "Ауа температурасы" },
  process_temperature: { ru: "Температура процесса", kk: "Процесс температурасы" },
  process_temperature_k: { ru: "Температура процесса", kk: "Процесс температурасы" },
  temp_diff: { ru: "Перегрев относительно воздуха", kk: "Ауаға қатысты қызу" },
  power: { ru: "Мощность", kk: "Қуат" },
  s_audio: { ru: "Звук станка", kk: "Станок дыбысы" },
  s_visual: { ru: "Фото инструмента/детали", kk: "Құрал/бөлшек суреті" },
  s_overdue: { ru: "Просрочка ТО", kk: "ТҚ мерзімінің өтуі" },
  s_history: { ru: "Недавние инциденты", kk: "Соңғы оқиғалар" },
  p_model: { ru: "Вероятность отказа (модель)", kk: "Ақау ықтималдығы (модель)" },
}

export function featureTitle(key: string, titleRu: string | undefined, lang: "ru" | "kk"): string {
  const known = FEATURES[key]
  if (lang === "kk" && known) return known.kk
  return titleRu || known?.ru || key
}
