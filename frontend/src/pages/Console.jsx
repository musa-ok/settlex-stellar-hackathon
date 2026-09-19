import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useAgentConsole } from '../hooks/useAgentConsole'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'
import PendingApprovals from '../components/PendingApprovals.jsx'

export default function Console() {
  const { t, language } = useLanguage()
  const auth = useAuth()
  const { turns, deal, settlement, fiatPayout, anchorSteps, negotiation, connected, resetSession } = useAgentConsole()
  const sellerEnd = useRef(null)
  const buyerEnd = useRef(null)
  const [busy, setBusy] = useState(false)
  const [invoiceAmount, setInvoiceAmount] = useState(480)
  const [supplier, setSupplier] = useState('Kağıt Tedarik A.Ş.')
  const [returnText, setReturnText] = useState('')
  const [signing, setSigning] = useState(false)

  const sellerTurns = turns.filter((t) => t.speaker === 'seller')
  const buyerTurns = turns.filter((t) => t.speaker === 'buyer')
  const pendingMultisig =
    !deal &&
    (negotiation?.status === 'pending_multisig' || negotiation?.status === 'awaiting_approval')
  const dealPrice = deal?.price ?? negotiation?.agreed_amount
  const txHash = settlement?.tx_hash || negotiation?.payment_tx
  const explorerUrl =
    settlement?.explorer_url ||
    (txHash ? `https://stellar.expert/explorer/testnet/tx/${txHash}` : null)

  useEffect(() => {
    sellerEnd.current?.scrollIntoView({ behavior: 'smooth' })
    buyerEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  async function sendInvoice() {
    if (!auth.authenticated) {
      try {
        await auth.login()
      } catch {
        await auth.register()
      }
    }
    resetSession()
    setBusy(true)
    try {
      await api.sendInvoice({
        supplier,
        product: 'bardak',
        quantity: 500,
        amount: Number(invoiceAmount) || 480,
        lang: language,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="eyebrow">Settlex · Agent-to-Agent</p>
          <h1 className="mt-1 text-3xl font-bold text-ink sm:text-4xl">{t('Canlı Ajan Konsolu', 'Live Agent Console')}</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink/60 sm:text-base">{t('Satıcı solda, alıcı sağda — her tur WebSocket ile akar.', 'Seller on the left, buyer on the right — each turn flows via WebSocket.')}</p>
        </div>
        <span className={`inline-flex w-fit items-center gap-2 rounded-full px-3.5 py-2 font-mono text-xs font-medium ring-1 ${connected ? 'bg-mint/10 text-mint-dim ring-mint/30' : 'bg-red-50 text-danger ring-danger/25'}`}>
          <span
            className={`h-2 w-2 rounded-full ${connected ? 'animate-pulse-dot bg-mint-dim' : 'bg-danger'}`}
          />
          {connected ? t('WebSocket canlı', 'WebSocket live') : t('yeniden bağlanıyor…', 'reconnecting…')}
        </span>
      </header>

      <section className="card space-y-4 p-4 sm:p-6">
        <div>
          <h2 className="text-lg font-bold text-ink sm:text-xl">{t('Demo Simülasyon Paneli', 'Demo Simulation Panel')}</h2>
          <p className="mt-1 text-sm text-ink/55">{t('B2B fatura veya B2C iade akışını tetikle.', 'Trigger B2B invoice or B2C return flow.')}</p>
        </div>
        {!auth.authenticated && (
          <div className="rounded-2xl border border-mint/40 bg-gradient-to-br from-mint/15 to-mint/5 p-4 sm:p-5">
            <p className="text-sm font-semibold leading-relaxed text-ink">
              {t('Ajanları tetiklemeden önce Passkey (FaceID / TouchID / Windows Hello) ile giriş yapın.', 'Login with Passkey (FaceID / TouchID / Windows Hello) before triggering agents.')}
            </p>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
              <button
                type="button"
                disabled={auth.busy}
                onClick={() => auth.login().catch(() => {})}
                className="btn btn-primary"
              >
                {t('Passkey ile giriş', 'Login with Passkey')}
              </button>
              <button
                type="button"
                disabled={auth.busy}
                onClick={() => auth.register().catch(() => {})}
                className="btn btn-ghost"
              >
                {t('Passkey kaydet', 'Register Passkey')}
              </button>
            </div>
            {auth.error && <p className="mt-2 break-words text-xs text-danger">{auth.error}</p>}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card-inset flex flex-col p-4 sm:p-5">
            <div className="flex items-center gap-2">
              <span className="chip bg-violet-100 text-violet-800">B2B</span>
              <h3 className="text-sm font-bold text-ink">
                {t('B2B: Kurumsal Fatura Akışı', 'B2B: Corporate Invoice Flow')}
              </h3>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block min-w-0">
                <span className="field-label">
                  {t('Tedarikçi', 'Supplier')}
                </span>
                <input
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                  className="field"
                />
              </label>
              <label className="block min-w-0">
                <span className="field-label">
                  {t('Tutar (TL)', 'Amount (TL)')}
                </span>
                <input
                  type="number"
                  min="1"
                  value={invoiceAmount}
                  onChange={(e) => setInvoiceAmount(e.target.value)}
                  className="field tabular-nums"
                />
              </label>
            </div>
            <div className="mt-4 flex flex-col gap-2 sm:mt-auto sm:flex-row sm:pt-4">
              <button
                type="button"
                disabled={busy || !auth.authenticated}
                onClick={sendInvoice}
                className="btn btn-primary w-full"
              >
                {busy ? t('Pazarlık…', 'Negotiating…') : t('Faturayı Gönder (Süreci Tetikle)', 'Send Invoice (Trigger Process)')}
              </button>
            </div>
          </div>

          <div className="card-inset flex flex-col p-4 sm:p-5">
            <div className="flex items-center gap-2">
              <span className="chip bg-sky-100 text-sky-800">B2C</span>
              <h3 className="text-sm font-bold text-ink">
                {t('B2C: Müşteri İade Akışı', 'B2C: Customer Return Flow')}
              </h3>
            </div>
            <label className="mt-4 block">
              <span className="field-label">{t('İade talebi', 'Return request')}</span>
              <input
                type="text"
                value={returnText}
                onChange={(e) => setReturnText(e.target.value)}
                placeholder={t('İade edilecek ürünü ve fiyatını yazın. Örn: Siyah Deri Ceket, 5000 TL', 'Type the product to return and its price. e.g.: Black Leather Jacket, 5000 TL')}
                className="field"
              />
            </label>
            <button
              type="button"
              disabled={busy || !auth.authenticated}
              onClick={async () => {
                if (!auth.authenticated) return
                resetSession()
                setBusy(true)
                try {
                  await api.startReturn(returnText, language)
                } finally {
                  setBusy(false)
                }
              }}
              className="btn btn-ghost mt-4 w-full sm:mt-auto"
            >
              {t('Müşteri İadesi (B2C Modülü)', 'Customer Return (B2C Module)')}
            </button>
          </div>
        </div>
      </section>

      {deal && (
        <div className="space-y-3">
          <div className="animate-deal relative overflow-hidden rounded-3xl bg-gradient-to-br from-mint to-[#8ff0c3] px-5 py-7 text-center shadow-[var(--shadow-lift)] sm:px-6 sm:py-9">
            <p className="eyebrow text-ink/60">Settlement</p>
            <p className="mt-2 font-display text-2xl font-bold tracking-tight text-ink sm:text-4xl">
              {t('MUTABAKAT SAĞLANDI', 'AGREEMENT REACHED')} — <span className="tabular-nums">{Number(dealPrice).toFixed(0)} TL</span>
            </p>
          </div>
          {explorerUrl && (
            <a
              href={explorerUrl}
              target="_blank"
              rel="noreferrer"
              className="explorer-glow block rounded-3xl bg-ink px-5 py-5 text-center no-underline transition hover:bg-panel sm:px-6"
            >
              <p className="font-display text-base font-bold text-mint sm:text-xl">
                View Settlement on Stellar Expert ↗
              </p>
              <p className="mt-2 break-all font-mono text-[11px] text-mint/70 sm:text-xs">
                {explorerUrl}
              </p>
            </a>
          )}
          {fiatPayout && <FiatPayoutCard payout={fiatPayout} t={t} />}
          {anchorSteps.length > 0 && (
            <ol className="space-y-1 rounded-3xl bg-ink p-4 font-mono text-xs shadow-[var(--shadow-soft)] sm:p-5 sm:text-sm">
              {anchorSteps.map((step, i) => {
                const text = typeof step === 'string' ? step : step.message
                const level = typeof step === 'string' ? 'info' : step.level
                const warn = level === 'warn'
                return (
                  <li
                    key={`${text}-${i}`}
                    className={`animate-fade-up flex gap-2 break-words rounded-xl px-2 py-1.5 ${warn ? 'bg-warn/10 font-semibold text-warn' : 'text-mint'}`}
                  >
                    <span className="shrink-0 opacity-50">{i + 1}.</span>
                    <span className="min-w-0">{text}</span>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      )}

      <PendingApprovals refreshKey={`${negotiation?.id}:${negotiation?.status}:${settlement?.tx_hash}`} />

      <div className="grid gap-4 lg:grid-cols-2 lg:gap-6">
        <ChatColumn
          title={t('Satıcı Ajan', 'Seller Agent')}
          subtitle={t('fatura / teklif', 'invoice / offer')}
          turns={sellerTurns}
          side="left"
          endRef={sellerEnd}
          t={t}
        />
        <ChatColumn
          title={t('Alıcı Ajan', 'Buyer Agent')}
          subtitle={t('kural / karşı teklif', 'rule / counter offer')}
          turns={buyerTurns}
          side="right"
          endRef={buyerEnd}
          t={t}
        />
      </div>

      {pendingMultisig && (
        <div className="card overflow-hidden border-orange-300/60">
          <div className="bg-gradient-to-r from-orange-50 to-amber-50/40 px-4 py-5 sm:px-6">
            <p className="font-display text-base font-bold leading-snug text-orange-800 sm:text-xl">
              {t('Anormal Tutar Tespit Edildi - Güvenlik Protokolü Gereği Yönetici (CFO) Multi-Sig İmzası Bekleniyor', 'Abnormal Amount Detected - Manager (CFO) Multi-Sig Signature Required per Security Protocol')}
            </p>
            <p className="mt-2 break-words text-sm leading-relaxed text-ink/70">
              {negotiation?.anomaly_reason ||
                t('İşlem iptal edilmedi; Stellar çoklu imza kilidinde donduruldu.', 'Transaction not canceled; frozen in Stellar multi-signature lock.')}
            </p>
            <button
              type="button"
              disabled={signing || !negotiation?.id}
              onClick={async () => {
                setSigning(true)
                try {
                  await api.approveMultisig(negotiation.id)
                } finally {
                  setSigning(false)
                }
              }}
              className="btn mt-4 w-full bg-orange-600 font-bold text-white shadow-lg shadow-orange-600/20 hover:bg-orange-500 sm:w-auto sm:px-6"
            >
              {signing
                ? t('İkinci imza atılıyor…', 'Signing second signature…')
                : t('Yönetici Onayı (İkinci İmzayı At ve Kilidi Aç)', 'Manager Approval (Sign Second and Unlock)')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// The anchor's own record of the TRY leg (SEP-6 /transaction), shown as proof next to the Stellar tx.
function FiatPayoutCard({ payout, t }) {
  const done = payout.status === 'completed'
  return (
    <div className={`card overflow-hidden ${done ? 'ring-1 ring-mint/40' : 'ring-1 ring-warn/40'}`}>
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="flex min-w-0 items-center gap-4">
          <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl font-display text-xl font-bold ${done ? 'bg-mint/15 text-mint-dim' : 'bg-warn/15 text-warn'}`}>
            ₺
          </span>
          <div className="min-w-0">
            <p className="eyebrow">{t('Anchor TL Ödemesi · SEP-6', 'Anchor TRY Payout · SEP-6')}</p>
            <p className="mt-1 font-display text-2xl font-bold tabular-nums tracking-tight text-ink sm:text-3xl">
              {payout.amount_out ?? '—'} <span className="text-base font-semibold text-ink/40">{payout.currency}</span>
            </p>
          </div>
        </div>
        <span className={`chip w-fit ${done ? 'bg-mint/15 text-mint-dim' : 'bg-warn/15 text-warn'}`}>
          {done ? t('Tamamlandı', 'Completed') : payout.status}
        </span>
      </div>
      <dl className="grid gap-x-4 gap-y-1.5 border-t border-ink/[0.06] bg-sand/30 px-5 py-4 text-sm sm:grid-cols-[auto_minmax(0,1fr)] sm:px-6">
        <dt className="text-ink/45">{t('Gönderilen', 'Sent')}</dt>
        <dd className="font-medium tabular-nums text-ink">{payout.amount_in} USDC</dd>
        <dt className="text-ink/45">{t('Anchor kesintisi', 'Anchor fee')}</dt>
        <dd className="font-medium tabular-nums text-ink">{payout.amount_fee} {payout.currency}</dd>
        {payout.external_transaction_id && (
          <>
            <dt className="text-ink/45">{t('Banka referansı', 'Bank reference')}</dt>
            <dd className="break-all font-mono text-xs text-ink">{payout.external_transaction_id}</dd>
          </>
        )}
        <dt className="text-ink/45">Anchor</dt>
        <dd className="break-all font-mono text-xs text-ink">{payout.anchor}</dd>
        {payout.message && (
          <>
            <dt className="text-ink/45">{t('Anchor mesajı', 'Anchor message')}</dt>
            <dd className="break-words text-ink/70">{payout.message}</dd>
          </>
        )}
      </dl>
    </div>
  )
}

function ChatColumn({ title, turns, side, endRef, subtitle, t }) {
  const isSeller = side === 'left'
  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="flex items-center gap-3 border-b border-ink/[0.06] bg-white px-4 py-3">
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-full font-display text-sm font-bold ${
            isSeller ? 'bg-amber-100 text-amber-800' : 'bg-sky-100 text-sky-800'
          }`}
        >
          {isSeller ? 'S' : 'B'}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-bold text-ink sm:text-base">
            {title}
          </h2>
          <p className="truncate text-xs text-ink/45">{subtitle}</p>
        </div>
        <span className="chip shrink-0 bg-ink/5 font-mono normal-case tracking-normal text-ink/55">{turns.length} {t('mesaj', 'messages')}</span>
      </div>
      <div className="terminal-scroll chat-wallpaper flex h-[22rem] flex-col gap-2.5 overflow-y-auto px-3 py-4 sm:h-[28rem] sm:px-4 lg:h-[32rem]">
        {turns.length === 0 && (
          <div className="m-auto flex flex-col items-center gap-2 text-center">
            <span className="flex gap-1">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-ink/20" />
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-ink/20" style={{ animationDelay: '0.2s' }} />
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-ink/20" style={{ animationDelay: '0.4s' }} />
            </span>
            <p className="text-sm text-ink/40">{t('Bekleniyor…', 'Waiting…')}</p>
          </div>
        )}
        {turns.map((t, i) => (
          <div
            key={`${t.speaker}-${t.price}-${i}`}
            className={`flex ${isSeller ? 'justify-start' : 'justify-end'} animate-fade-up`}
          >
            <div
              className={`relative max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-relaxed shadow-sm sm:max-w-[80%] sm:text-sm ${
                isSeller
                  ? 'rounded-tl-md bg-white text-ink ring-1 ring-ink/[0.05]'
                  : 'rounded-tr-md bg-[#d6f7e6] text-ink ring-1 ring-mint/30'
              }`}
            >
              <p className="whitespace-pre-wrap break-words">{t.message}</p>
              <div className="mt-1.5 flex items-center justify-end gap-2">
                {t.status === 'deal' && (
                  <span className="chip bg-mint-dim px-2 py-0.5 text-[10px] text-white">Deal ✓</span>
                )}
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-xs font-semibold tabular-nums ${
                    isSeller ? 'bg-amber-100 text-amber-900' : 'bg-white/70 text-mint-dim'
                  }`}
                >
                  {Number(t.price).toFixed(0)} TL
                </span>
              </div>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}
