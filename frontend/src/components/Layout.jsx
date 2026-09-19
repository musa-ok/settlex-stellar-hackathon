import { NavLink } from 'react-router-dom'
import JuryBadges from './JuryBadges'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Layout({ children }) {
  const { language, toggleLanguage, t } = useLanguage()
  const auth = useAuth()

  const links = [
    { to: '/', label: t('Giriş', 'Onboarding'), end: true },
    { to: '/rules', label: t('Kurallar', 'Rules') },
    { to: '/console', label: t('Ajan Konsolu', 'Agent Console') },
    { to: '/balance', label: t('Bakiye', 'Balance') },
    { to: '/supplier', label: t('Tedarikçi', 'Supplier') },
  ]

  return (
    <div className="flex min-h-screen flex-col">
      <header className="z-40 border-b border-ink/[0.06] bg-white/70 backdrop-blur-xl lg:sticky lg:top-0">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-3 px-4 pt-3 pb-2 sm:px-6 lg:flex-nowrap lg:py-3">
          <NavLink to="/" className="order-1 group flex min-w-0 items-center gap-3 no-underline">
            <img src="/logo.png" alt="" className="h-9 w-9 shrink-0 rounded-xl shadow-md shadow-ink/20" />
            <span className="font-display text-xl font-bold tracking-tight text-ink sm:text-2xl">
              Settlex
            </span>
            <span className="hidden 2xl:flex">
              <JuryBadges />
            </span>
          </NavLink>

          <nav className="no-scrollbar order-4 -mx-4 flex w-full items-center gap-1.5 overflow-x-auto px-4 pb-1 text-sm [mask-image:linear-gradient(to_right,black_85%,transparent)] sm:-mx-6 sm:[mask-image:none] sm:px-6 lg:order-2 lg:mx-0 lg:w-auto lg:flex-1 lg:justify-center lg:px-0 lg:pb-0">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `inline-flex min-h-10 shrink-0 items-center whitespace-nowrap rounded-full px-4 font-medium transition-colors ${
                    isActive
                      ? 'bg-ink text-mint shadow-md shadow-ink/15'
                      : 'text-ink/65 hover:bg-ink/5 hover:text-ink'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <button
            onClick={toggleLanguage}
            className="order-2 ml-auto flex min-h-10 items-center gap-2 rounded-full border border-ink/10 bg-white px-3.5 text-xs font-bold uppercase tracking-wider text-ink shadow-sm transition-all hover:border-ink/25 lg:order-3 lg:ml-0"
          >
            <span className={language === 'tr' ? 'text-mint-dim' : 'text-ink/35'}>TR</span>
            <span className="text-ink/15">|</span>
            <span className={language === 'en' ? 'text-mint-dim' : 'text-ink/35'}>EN</span>
          </button>

          <div className="order-3 w-full sm:w-auto lg:order-4">
            {auth.authenticated ? (
              <button
                type="button"
                onClick={() => auth.logout()}
                className="flex min-h-10 w-full items-center justify-center gap-2 rounded-full bg-mint/15 px-4 text-[11px] font-bold uppercase tracking-wide text-ink ring-1 ring-mint/40 transition hover:bg-mint/25 sm:w-auto"
              >
                <span className="h-2 w-2 rounded-full bg-mint-dim" />
                {t('Passkey', 'Passkey')} · {auth.username}
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:flex">
                <button
                  type="button"
                  disabled={auth.busy}
                  onClick={() => auth.register()}
                  className="min-h-10 rounded-full border border-ink/15 bg-white px-4 text-[11px] font-bold uppercase tracking-wide text-ink transition hover:border-ink/30 disabled:opacity-50"
                >
                  {auth.busy ? t('Kaydediliyor…', 'Registering…') : t('Register Passkey', 'Register Passkey')}
                </button>
                <button
                  type="button"
                  disabled={auth.busy}
                  onClick={() => auth.login()}
                  className="min-h-10 rounded-full bg-ink px-4 text-[11px] font-bold uppercase tracking-wide text-mint shadow-md shadow-ink/15 transition hover:bg-ink-soft disabled:opacity-50"
                >
                  {auth.busy ? t('Doğrulanıyor…', 'Verifying…') : t('Login Passkey', 'Login Passkey')}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-10">{children}</main>
      <footer className="border-t border-ink/[0.06] px-4 py-6 text-center text-xs text-ink/45">
        <div className="mb-3 flex justify-center 2xl:hidden">
          <JuryBadges />
        </div>
        Settlex · Pro Hackathon 2026 Genesis Track · Rise In × Stellar
      </footer>
    </div>
  )
}
