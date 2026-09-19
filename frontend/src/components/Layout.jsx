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
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b border-ink/10 bg-sand/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <NavLink to="/" className="group flex min-w-0 flex-col gap-1 no-underline sm:flex-row sm:items-center sm:gap-3">
            <span className="font-display text-2xl font-bold tracking-tight text-ink">
              Settlex
            </span>
            <JuryBadges />
          </NavLink>
          <div className="flex items-center gap-4">
            <nav className="flex flex-wrap items-center gap-1 text-sm">
              {links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-1.5 font-medium transition-colors ${
                      isActive
                        ? 'bg-ink text-mint'
                        : 'text-ink/70 hover:bg-ink/5 hover:text-ink'
                    }`
                  }
                >
                  {l.label}
                </NavLink>
              ))}
            </nav>
            <button
              onClick={toggleLanguage}
              className="flex items-center gap-2 rounded-full border border-ink/20 bg-white/50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-ink transition-all hover:bg-white"
            >
              <span className={language === 'tr' ? 'text-mint' : 'text-ink/40'}>TR</span>
              <span className="text-ink/20">|</span>
              <span className={language === 'en' ? 'text-mint' : 'text-ink/40'}>EN</span>
            </button>
            {auth.authenticated ? (
              <button
                type="button"
                onClick={() => auth.logout()}
                className="rounded-full bg-mint/20 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-ink"
              >
                {t('Passkey', 'Passkey')} · {auth.username}
              </button>
            ) : (
              <button
                type="button"
                disabled={auth.busy}
                onClick={() => auth.login().catch(() => auth.register().catch(() => {}))}
                className="rounded-full bg-ink px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-mint"
              >
                {auth.busy ? t('Doğrulanıyor…', 'Verifying…') : t('Passkey ile giriş', 'Login with Passkey')}
              </button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
      <footer className="border-t border-ink/10 py-4 text-center text-xs text-ink/45">
        Settlex · Pro Hackathon 2026 Genesis Track · Rise In × Stellar
      </footer>
    </div>
  )
}
