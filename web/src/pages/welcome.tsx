import { useState } from "react"
import {
  ArrowDownIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronRightIcon,
  CrosshairIcon,
  FactoryIcon,
  ScanLineIcon,
  XIcon,
} from "lucide-react"
import { Link } from "react-router"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from "recharts"

import { Brand } from "@/components/brand"
import { LangToggle, ThemeToggle } from "@/components/toggles"
import { Button } from "@/components/ui/button"

import { useI18n } from "@/i18n"
import "./welcome.css"

const production = [
  { time: "08:00", value: 21 },
  { time: "09:00", value: 28 },
  { time: "10:00", value: 25 },
  { time: "11:00", value: 34 },
  { time: "12:00", value: 32 },
  { time: "13:00", value: 42 },
  { time: "14:00", value: 38 },
]

function PlatformPreview({ kk }: { kk: boolean }) {
  const [selected, setSelected] = useState(0)
  const [showRegion, setShowRegion] = useState(true)
  const copy = (ru: string, kz: string) => (kk ? kz : ru)
  const rows = [
    { id: "BR-0248", time: "14:32", issue: true },
    { id: "BR-0247", time: "14:31", issue: false },
    { id: "BR-0246", time: "14:30", issue: false },
  ]
  const current = rows[selected]
  return (
    <div className="platform-preview" id="platform-preview">
      <div className="preview-topbar">
        <span className="preview-brand">
          <ScanLineIcon /> Fibo <span>/</span> {copy("Производство", "Өндіріс")}
        </span>
        <span className="demo-label">
          {copy("Демо · пример данных", "Демо · деректер үлгісі")}
        </span>
      </div>
      <div className="preview-content">
        <div className="preview-heading">
          <div>
            <span className="preview-eyebrow">
              {copy("Контроль качества", "Сапаны бақылау")}
            </span>
            <h2>{copy("Каждая деталь на виду", "Әр бөлшек назарда")}</h2>
          </div>
          <span className="line-label">{copy("Линия", "Желі")} 02</span>
        </div>
        <div className="inspection-grid">
          <div className="inspection-image">
            <img
              src="/images/roller-bearing.jpg"
              alt={copy(
                "Крупный план стального роликового подшипника",
                "Болат роликті мойынтіректің жақыннан көрінісі"
              )}
              width="1670"
              height="1500"
              fetchPriority="high"
            />
            <span className="image-meta">
              {current.id} <span>CAM 02</span>
            </span>
            {current.issue && showRegion && (
              <div className="defect-region">
                <span>{copy("Область проверки", "Тексеру аймағы")}</span>
                <i />
                <i />
                <i />
                <i />
              </div>
            )}
            <button
              className="image-control"
              aria-pressed={showRegion}
              onClick={() => setShowRegion(!showRegion)}
            >
              <CrosshairIcon />
              {copy("Разметка", "Белгілеу")}
              <span>{showRegion ? "On" : "Off"}</span>
            </button>
          </div>
          <div className="inspection-result" aria-live="polite">
            <span className="preview-eyebrow">
              {copy("Результат проверки", "Тексеру нәтижесі")}
            </span>
            <div
              className={
                current.issue
                  ? "inspection-status warning"
                  : "inspection-status passed"
              }
            >
              {current.issue ? <CrosshairIcon /> : <CheckIcon />}
              {current.issue
                ? copy("Нужна проверка", "Тексеру қажет")
                : copy("Без замечаний", "Ескерту жоқ")}
            </div>
            <h3>
              {current.issue
                ? copy("След на поверхности", "Беткі із")
                : copy("Поверхность в норме", "Беті қалыпты")}
            </h3>
            <p>
              {current.issue
                ? copy(
                    "Предполагаемый дефект внутреннего кольца. Передайте деталь контролёру.",
                    "Ішкі сақинада ақау болуы мүмкін. Бөлшекті бақылаушыға беріңіз."
                  )
                : copy(
                    "В этом примере отклонений не обнаружено. Деталь прошла проверку.",
                    "Бұл мысалда ауытқу анықталмады. Бөлшек тексеруден өтті."
                  )}
            </p>
            <dl>
              <div>
                <dt>{copy("Изделие", "Бұйым")}</dt>
                <dd>{copy("Подшипник", "Мойынтірек")}</dd>
              </div>
              <div>
                <dt>{copy("Метод", "Әдіс")}</dt>
                <dd>{copy("Фотоанализ", "Фототалдау")}</dd>
              </div>
              <div>
                <dt>{copy("Проверка", "Тексеру")}</dt>
                <dd>{current.time}</dd>
              </div>
            </dl>
          </div>
        </div>
        <div className="preview-bottom">
          <div className="inspection-log">
            <h3>
              {copy("Последние проверки", "Соңғы тексерулер")}
              <span>3</span>
            </h3>
            <table>
              <thead>
                <tr>
                  <th>{copy("Изделие", "Бұйым")}</th>
                  <th>{copy("Время", "Уақыт")}</th>
                  <th>{copy("Результат", "Нәтиже")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={row.id}
                    className={selected === index ? "selected" : ""}
                  >
                    <td>
                      <button
                        onClick={() => setSelected(index)}
                        aria-pressed={selected === index}
                      >
                        {row.id}
                        <ChevronRightIcon />
                      </button>
                    </td>
                    <td>{row.time}</td>
                    <td className={row.issue ? "table-warning" : "table-pass"}>
                      {row.issue
                        ? copy("На проверку", "Тексеруге")
                        : copy("Годен", "Жарамды")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="equipment-panel">
            <h3>
              {copy("Состояние линии", "Желі күйі")}
              <span className="status-dot" />
            </h3>
            <div className="machine-status">
              <FactoryIcon />
              <span>
                {copy("Станок ЧПУ-02", "СББ станогы-02")}
                <small>
                  {copy("В работе · без отклонений", "Жұмыста · ауытқусыз")}
                </small>
              </span>
            </div>
            <div className="output-label">
              <span>{copy("Проверено за час", "Сағатына тексерілді")}</span>
              <strong>
                38 <small>{copy("шт.", "дана")}</small>
              </strong>
            </div>
            <div className="production-chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={production}
                  margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
                >
                  <CartesianGrid
                    vertical={false}
                    stroke="var(--preview-line)"
                  />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 10, fill: "var(--preview-muted)" }}
                    ticks={["08:00", "11:00", "14:00"]}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={12}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--preview-bg)",
                      border: "1px solid var(--preview-line)",
                      borderRadius: 4,
                      fontSize: 12,
                    }}
                    formatter={(value) => [
                      value,
                      copy("Проверено", "Тексерілді"),
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#4a9eff"
                    strokeWidth={2}
                    fill="#4a9eff"
                    fillOpacity={0.09}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
      <div className="preview-footer">
        <span>
          {copy(
            "Пример интерфейса · разметка иллюстративная",
            "Интерфейс үлгісі · белгілеу мысал ретінде"
          )}
        </span>
        <span>Fibo / 02</span>
      </div>
    </div>
  )
}

export function WelcomePage() {
  const { lang } = useI18n()
  const kk = lang === "kk"
  const copy = (ru: string, kz: string) => (kk ? kz : ru)
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="fibo-landing">
      <header className="landing-header landing-container">
        <Link to="/" aria-label="Fibo — главная">
          <Brand />
        </Link>
        <nav
          aria-label={copy("Основная навигация", "Негізгі навигация")}
          className={menuOpen ? "landing-nav is-open" : "landing-nav"}
        >
          <a href="#platform-preview" onClick={() => setMenuOpen(false)}>
            {copy("Платформа", "Платформа")}
          </a>
        </nav>
        <div className="header-actions">
          <LangToggle />
          <ThemeToggle />
          <Link className="login-link" to="/login">
            {copy("Войти", "Кіру")}
          </Link>
          <Button asChild className="landing-button header-cta">
            <Link to="/start">
              {copy("Создать аккаунт", "Аккаунт ашу")}
              <ArrowRightIcon />
            </Link>
          </Button>
          <Button
            className="mobile-menu"
            size="icon"
            variant="ghost"
            aria-label={copy("Меню", "Мәзір")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <XIcon /> : <span className="menu-lines" />}
          </Button>
        </div>
      </header>
      <main>
        <section className="landing-hero landing-container">
          <div className="hero-copy">
            <div className="hero-kicker">
              <span />
              {copy(
                "Контроль производства с Fibo",
                "Fibo көмегімен өндірісті бақылау"
              )}
            </div>
            <h1>
              {copy("Качество видно.", "Сапа көрінеді.")}
              <br />
              {copy("Производство", "Өндіріс")}
              <br />
              <span>{copy("под контролем.", "бақылауда.")}</span>
            </h1>
            <p>
              {copy(
                "Fibo помогает обнаруживать дефекты продукции, анализировать состояние оборудования и отслеживать производственные показатели в едином интерфейсе.",
                "Fibo өнім ақауларын анықтауға, жабдықтың күйін талдауға және өндіріс көрсеткіштерін бір интерфейсте бақылауға көмектеседі."
              )}
            </p>
            <div className="hero-actions">
              <Button asChild size="lg" className="landing-button">
                <Link to="/start">
                  {copy("Зарегистрироваться", "Тіркелу")}
                  <ArrowRightIcon />
                </Link>
              </Button>
              <a className="preview-link" href="#platform-preview">
                {copy("Посмотреть интерфейс", "Интерфейсті көру")}
                <ArrowDownIcon />
              </a>
            </div>
            <div className="hero-caption">
              {copy(
                "Отдельная деталь. Вся производственная линия.",
                "Жеке бөлшек. Бүкіл өндіріс желісі."
              )}
            </div>
          </div>
          <PlatformPreview kk={kk} />
        </section>
        <section className="landing-cta landing-container">
          <div>
            <span className="section-number">
              02 / {copy("Ваше производство", "Сіздің өндірісіңіз")}
            </span>
            <h2>
              {copy("Начните с вашего", "Өз өндірісіңізден")}
              <br />
              {copy("производства", "бастаңыз")}
            </h2>
            <p>
              {copy(
                "Создайте аккаунт и добавьте оборудование в Fibo.",
                "Аккаунт ашып, жабдықты Fibo жүйесіне қосыңыз."
              )}
            </p>
          </div>
          <Button asChild size="lg" className="landing-button">
            <Link to="/start">
              {copy("Создать аккаунт", "Аккаунт ашу")}
              <ArrowRightIcon />
            </Link>
          </Button>
        </section>
      </main>
      <footer className="landing-footer landing-container">
        <Brand />
        <span>Fibo · {copy("Шымкент, Казахстан", "Шымкент, Қазақстан")}</span>
        <span>
          {copy("Русский и казахский язык", "Орыс және қазақ тілдері")}
        </span>
      </footer>
    </div>
  )
}
