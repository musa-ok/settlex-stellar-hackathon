import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useAgentConsole } from '../hooks/useAgentConsole'
import { useLanguage } from '../hooks/useLanguage.jsx'

export default function Console() {
  const { t, language } = useLanguage()
  const { turns, deal, anchorSteps, negotiation, connected, resetSession } = useAgentConsole()
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

  useEffect(() => {
    sellerEnd.current?.scrollIntoView({ behavior: 'smooth' })
    buyerEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  async function sendInvoice() {
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
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold text-ink">{t('Canlı Ajan Konsolu', 'Live Agent Console')}</h1>
          <p className="mt-1 text-ink/60">{t('Satıcı solda, alıcı sağda — her tur WebSocket ile akar.', 'Seller on the left, buyer on the right — each turn flows via WebSocket.')}</p>
        </div>
        <span className="inline-flex items-center gap-2 font-mono text-xs text-ink/55">
          <span
            className={`h-2 w-2 rounded-full ${connected ? 'animate-pulse-dot bg-mint-dim' : 'bg-danger'}`}
          />
          {connected ? t('WebSocket canlı', 'WebSocket live') : t('yeniden bağlanıyor…', 'reconnecting…')}
        </span>
      </header>

      <section className="space-y-4 rounded-2xl border border-ink/10 bg-white/80 p-5 shadow-sm">
        <h2 className="font-display text-xl font-semibold text-ink">{t('Demo Simülasyon Paneli', 'Demo Simulation Panel')}</h2>
        <p className="text-sm text-ink/50">{t('B2B fatura veya B2C iade akışını tetikle.', 'Trigger B2B invoice or B2C return flow.')}</p>

        <div className="rounded-xl border border-ink/10 bg-sand/30 p-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-ink/70">
            {t('B2B: Kurumsal Fatura Akışı', 'B2B: Corporate Invoice Flow')}
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                {t('Tedarikçi', 'Supplier')}
              </span>
              <input
                value={supplier}
                onChange={(e) => setSupplier(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink/15 bg-white/80 px-3 py-2.5 outline-none focus:ring-2 focus:ring-mint"
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                {t('Tutar (TL)', 'Amount (TL)')}
              </span>
              <input
                type="number"
                min="1"
                value={invoiceAmount}
                onChange={(e) => setInvoiceAmount(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink/15 bg-white/80 px-3 py-2.5 outline-none focus:ring-2 focus:ring-mint"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={busy}
              onClick={sendInvoice}
              className="flex-1 rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-mint disabled:opacity-50"
            >
              {busy ? t('Pazarlık…', 'Negotiating…') : t('Faturayı Gönder (Süreci Tetikle)', 'Send Invoice (Trigger Process)')}
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-ink/10 bg-sand/30 p-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-ink/70">
            {t('B2C: Müşteri İade Akışı', 'B2C: Customer Return Flow')}
          </h3>
          <label className="mt-3 block">
            <span className="sr-only">{t('İade talebi', 'Return request')}</span>
            <input
              type="text"
              value={returnText}
              onChange={(e) => setReturnText(e.target.value)}
              placeholder={t('İade edilecek ürünü ve fiyatını yazın. Örn: Siyah Deri Ceket, 5000 TL', 'Type the product to return and its price. e.g.: Black Leather Jacket, 5000 TL')}
              className="w-full rounded-xl border border-ink/15 bg-white/80 px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-mint"
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              resetSession()
              setBusy(true)
              try {
                await api.startReturn(returnText, language)
              } finally {
                setBusy(false)
              }
            }}
            className="mt-3 w-full rounded-xl border border-ink/15 bg-white py-2.5 text-sm font-semibold text-ink disabled:opacity-50"
          >
            {t('Müşteri İadesi (B2C Modülü)', 'Customer Return (B2C Module)')}
          </button>
        </div>
      </section>

      {deal && (
        <div className="space-y-3">
          <div className="animate-deal rounded-2xl border-2 border-mint bg-mint px-6 py-8 text-center shadow-lg">
            <p className="font-display text-3xl font-bold tracking-tight text-ink md:text-4xl">
              {t('MUTABAKAT SAĞLANDI', 'AGREEMENT REACHED')} — {Number(dealPrice).toFixed(0)} TL
            </p>
          </div>
          {anchorSteps.length > 0 && (
            <ol className="rounded-2xl border border-ink/10 bg-ink p-5 font-mono text-sm">
              {anchorSteps.map((step, i) => {
                const text = typeof step === 'string' ? step : step.message
                const level = typeof step === 'string' ? 'info' : step.level
                const warn = level === 'warn'
                return (
                  <li
                    key={`${text}-${i}`}
                    className={`animate-fade-up py-1.5 ${warn ? 'font-semibold text-warn' : 'text-mint'}`}
                  >
                    {i + 1}. {text}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
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
        <div className="rounded-2xl border-2 border-orange-500 bg-orange-500/15 px-5 py-5 shadow-md">
          <p className="font-display text-lg font-bold text-orange-700 md:text-xl">
            {t('Anormal Tutar Tespit Edildi - Güvenlik Protokolü Gereği Yönetici (CFO) Multi-Sig İmzası Bekleniyor', 'Abnormal Amount Detected - Manager (CFO) Multi-Sig Signature Required per Security Protocol')}
          </p>
          <p className="mt-2 text-sm text-ink/70">
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
            className="mt-4 w-full rounded-xl bg-orange-600 py-3 text-sm font-bold text-white hover:bg-orange-500 disabled:opacity-50 sm:w-auto sm:px-6"
          >
            {signing
              ? t('İkinci imza atılıyor…', 'Signing second signature…')
              : t('Yönetici Onayı (İkinci İmzayı At ve Kilidi Aç)', 'Manager Approval (Sign Second and Unlock)')}
          </button>
        </div>
      )}
    </div>
  )
}

function ChatColumn({ title, turns, side, endRef, subtitle, t }) {
  const isSeller = side === 'left'
  return (
    <div
      className={`flex min-h-[420px] flex-col overflow-hidden rounded-2xl border ${
        isSeller ? 'border-amber-400/40' : 'border-sky-400/40'
      } bg-[#0c221a]`}
    >
      <div
        className={`flex items-center justify-between px-4 py-3 ${
          isSeller ? 'bg-amber-500/15' : 'bg-sky-500/15'
        }`}
      >
        <div>
          <h2 className={`text-sm font-semibold ${isSeller ? 'text-amber-200' : 'text-sky-200'}`}>
            {title}
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-widest text-sand/40">{subtitle}</p>
        </div>
        <span className="font-mono text-[10px] text-sand/35">{turns.length} {t('mesaj', 'messages')}</span>
      </div>
      <div className="terminal-scroll flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {turns.length === 0 && (
          <p className="mt-8 text-center text-sm text-sand/35">{t('Bekleniyor…', 'Waiting…')}</p>
        )}
        {turns.map((t, i) => (
          <div
            key={`${t.speaker}-${t.price}-${i}`}
            className={`flex ${isSeller ? 'justify-start' : 'justify-end'} animate-fade-up`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow ${
                isSeller
                  ? 'rounded-tl-sm bg-[#2a2418] text-amber-50'
                  : 'rounded-tr-sm bg-[#16382c] text-mint'
              }`}
            >
              <p>{t.message}</p>
              <p className={`mt-2 font-mono text-xs ${isSeller ? 'text-amber-200/70' : 'text-mint/80'}`}>
                {Number(t.price).toFixed(0)} TL
              </p>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}
