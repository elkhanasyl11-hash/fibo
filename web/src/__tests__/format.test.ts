import { describe, expect, it } from "vitest"

import { ago, kzt, kztShort, num, pct } from "@/lib/format"

const plain = (s: string) => s.replace(/[\u00a0\u202f]/g, " ")

describe("money and numbers", () => {
  it("formats tenge with spaces and no decimals", () => {
    expect(plain(kzt(186000))).toBe("186 000 ₸")
    expect(plain(kzt("54000.40"))).toBe("54 000 ₸")
    expect(kzt(null)).toBe("—")
  })
  it("uses the Kazakhstan number format in Kazakh too", () => {
    expect(plain(kzt(1234567, "kk"))).toBe("1 234 567 ₸")
    expect(num(0.53, 2, "kk")).toBe("0,53")
  })
  it("shortens big amounts for charts", () => {
    expect(plain(kztShort(1_250_000))).toBe("1,3 млн ₸")
    expect(plain(kztShort(340_000))).toBe("340 тыс ₸")
  })
  it("keeps one decimal below 10 percent", () => {
    expect(pct(0.25)).toBe("25%")
    expect(pct(0.012)).toBe("1,2%")
    expect(pct(null)).toBe("—")
  })
  it("prints relative time", () => {
    const now = Date.parse("2026-11-09T12:00:00Z")
    expect(ago("2026-11-09T11:55:00Z", "ru", now)).toBe("5 мин назад")
    expect(ago("2026-11-09T09:00:00Z", "ru", now)).toBe("3 ч назад")
  })
})
