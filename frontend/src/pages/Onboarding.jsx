import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext.jsx'
import { useWallet } from '../hooks/useWallet'
import { walletErrorText } from '../wallet'
import WalletPanel from '../components/WalletPanel.jsx'

export default function Onboarding() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const { error, success } = useToast()
  const auth = useAuth()
  const walletHook = useWallet()
  const wallet = walletHook.address
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  async function connectDemo() {
    setBusy(true)
    setStatus(t('Testnet hesabı oluşturuluyor…', 'Creating testnet account…'))
    try {
      const funded = await api.fundWallet()
      const pk = funded.public_key
      await api.connectWallet(pk)
      walletHook.setAddress(pk)
      setStatus(t('Demo cüzdan bağlandı · Friendbot fonladı', 'Demo wallet connected · Funded by Friendbot'))
      success(t('Cüzdan başarıyla bağlandı!', 'Wallet connected successfully!'))
    } catch (err) {
      console.error('Wallet connection error:', err)
      let errorMessage = t('Bağlantı hatası', 'Connection error')
      
      // Parse backend ErrorResponse
      if (err.response?.data) {
        const errorData = err.response.data
        if (errorData.error_code) {
          errorMessage = `${errorData.error}: ${errorData.message || errorData.error_code}`
        } else if (errorData.error) {
          errorMessage = errorData.error
        }
      } else if (err.message) {
        errorMessage = err.message
      }
      
      setStatus(errorMessage)
      error(errorMessage)
    } finally {
      setBusy(false)
    }
  }

  async function connectReal() {
    setBusy(true)
    try {
      const pk = await walletHook.connect()
      setStatus(t(`Cüzdan bağlandı: ${pk.slice(0, 6)}…${pk.slice(-4)}`, `Wallet connected: ${pk.slice(0, 6)}…${pk.slice(-4)}`))
      success(t('Cüzdan başarıyla bağlandı!', 'Wallet connected successfully!'))
    } catch (err) {
      const message = walletErrorText(err) || t('Bağlantı hatası', 'Connection error')
      setStatus(message)
      error(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 sm:space-y-8">
    <section className="relative overflow-hidden rounded-3xl bg-ink text-sand shadow-[var(--shadow-lift)]">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            'linear-gradient(rgba(61,220,151,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(61,220,151,0.07) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />
      <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-mint/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 left-10 h-64 w-64 rounded-full bg-mint-dim/30 blur-3xl" />

      <div className="relative grid gap-8 px-5 py-10 sm:px-8 sm:py-14 md:grid-cols-[1.2fr_0.8fr] md:gap-10 md:px-14 md:py-20">
        <div className="animate-fade-up">
          <p className="mb-4 font-mono text-xs uppercase tracking-[0.28em] text-mint">
            Stellar · Agent-to-Agent
          </p>
          <h1 className="text-5xl font-bold leading-[1.02] tracking-tight sm:text-6xl md:text-7xl">
            Settlex
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-sand/75 sm:text-lg">
            {t('Ajan pazarlık ediyor, sen sadece izliyorsun — ödeme gerçek TL\'ye dönüşüyor.', 'Agents negotiate, you just watch — payment turns into real TRY.')}
          </p>
          <div className="mt-8 grid gap-2.5 sm:mt-9 sm:flex sm:flex-wrap sm:gap-3">
            <button
              type="button"
              disabled={auth.busy}
              onClick={async () => {
                try {
                  await auth.login()
                  success(t('Passkey ile giriş başarılı', 'Passkey login successful'))
                } catch {
                  try {
                    await auth.register()
                    success(t('Passkey kaydedildi', 'Passkey registered'))
                  } catch (err) {
                    error(err.message || t('Passkey başarısız', 'Passkey failed'))
                  }
                }
              }}
              className="btn btn-mint w-full sm:w-auto"
            >
              {auth.busy
                ? t('FaceID / TouchID…', 'FaceID / TouchID…')
                : auth.authenticated
                  ? t('Passkey oturumu açık', 'Passkey session active')
                  : t('Passkey ile giriş', 'Login with Passkey')}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={connectReal}
              className="btn w-full bg-white/10 text-sand ring-1 ring-sand/20 hover:bg-white/15 sm:w-auto"
            >
              {busy ? t('Bağlanıyor…', 'Connecting…') : t('Cüzdan Bağla (Freighter)', 'Connect Wallet (Freighter)')}
            </button>
            <button
              type="button"
              onClick={() => navigate('/console')}
              className="btn w-full border border-sand/20 text-sand hover:border-mint hover:text-mint sm:w-auto"
            >
              {t('Ajan Konsoluna git', 'Go to Agent Console')}
            </button>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={connectDemo}
            className="mt-3 min-h-10 text-xs font-medium text-sand/55 underline decoration-sand/25 underline-offset-4 transition hover:text-mint disabled:opacity-50"
          >
            {t('Cüzdanın yok mu? Demo cüzdan (Friendbot)', 'No wallet? Use a demo wallet (Friendbot)')}
          </button>
          {status && (
            <p className="mt-4 break-words font-mono text-xs text-mint">{status}</p>
          )}
          {wallet && (
            <p className="mt-2 break-all font-mono text-[11px] text-sand/50">
              {wallet}
            </p>
          )}
        </div>

        <div className="animate-fade-up flex flex-col justify-end gap-4 delay-100" style={{ animationDelay: '120ms' }}>
          <div className="rounded-3xl border border-mint/20 bg-panel/80 p-5 font-mono text-xs leading-relaxed text-mint/90 shadow-2xl shadow-black/20 backdrop-blur">
            <div className="mb-3 flex items-center gap-2 text-sand/60">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-mint" />
              {t('canlı ajan', 'live agent')}
            </div>
            <p>&gt; {t('kural: max 450 TL · Kağıt Tedarik', 'rule: max 450 TL · Paper Supply')}</p>
            <p>&gt; {t('fatura: 480 TL — karşı teklif', 'invoice: 480 TL — counter offer')}</p>
            <p>&gt; {t('tur 2: 445 TL — DEAL', 'round 2: 445 TL — DEAL')}</p>
            <p className="text-sand">&gt; stellar settlement ✓</p>
          </div>
          <p className="text-sm text-sand/55">
            Testnet · {t('ajan pazarlığı', 'agent negotiation')} · SEP-6 / SEP-10
          </p>
        </div>
      </div>
    </section>

    <WalletPanel wallet={walletHook} />
    </div>
  )
}
