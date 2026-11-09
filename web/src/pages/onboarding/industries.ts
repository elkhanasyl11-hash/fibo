import { CakeSliceIcon, CogIcon, MilkIcon, ScissorsIcon, WheatIcon } from "lucide-react"

import type { Profile } from "@/lib/types"

export const INDUSTRIES: { id: Profile; icon: typeof CogIcon; ru: string; kk: string }[] = [
  { id: "metalworking", icon: CogIcon, ru: "Металлообработка", kk: "Металл өңдеу" },
  { id: "bakery", icon: WheatIcon, ru: "Пекарня", kk: "Наубайхана" },
  { id: "confectionery", icon: CakeSliceIcon, ru: "Кондитерская", kk: "Кондитерлік цех" },
  { id: "sewing", icon: ScissorsIcon, ru: "Швейный цех", kk: "Тігін цехы" },
  { id: "dairy", icon: MilkIcon, ru: "Молочное производство", kk: "Сүт өндірісі" },
]
