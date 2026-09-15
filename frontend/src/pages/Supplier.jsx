import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage'

export default function Supplier() {
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const [amount, setAmount] = useState(480)
  const [supplier, setSupplier] = useState('Kağıt Tedarik A.Ş.')
  const [returnText, setReturnText] = useState('')
  const [status, setStatus] = useState('')

  const SUSPICIOUS_AMOUNT = 1500

  function send(payload) {
    setStatus(t('Fatura gönderiliyor…', 'Sending invoice…'))
    void api.sendInvoice({ ...payload, lang: language }).catch((err) => console.error(err))
    navigate('/console')
  }

  function sendReturn() {
    setStatus(t('İade pazarlığı başlıyor…', 'Return negotiation starting…'))
    void api.startReturn(returnText, language).catch((err) => console.error(err))
    navigate('/console')
  }

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <header>
        <h1 className="font-display text-4xl font-bold text-ink">{t('Demo Simülasyon Paneli', 'Demo Simulation Panel')}</h1>
        <p className="mt-2 text-ink/60">
          {t('B2B kurumsal fatura veya B2C müşteri iadesi — ajan pazarlığını tetikle.', 'B2B corporate invoice or B2C customer return — trigger agent negotiation.')}
        </p>
      </header>

      <div className="space-y-4 rounded-2xl border border-ink/10 bg-white/70 p-6">
        <h2 className="text-sm font-bold uppercase tracking-wide text-ink/70">
          {t('B2B: Kurumsal Fatura Akışı', 'B2B: Corporate Invoice Flow')}
        </h2>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink/50">
          {t('Tedarikçi', 'Supplier')}
        </label>
        <input
          value={supplier}
          onChange={(e) => setSupplier(e.target.value)}
          className="w-full rounded-xl border border-ink/15 px-3 py-2.5 outline-none focus:ring-2 focus:ring-mint"
        />
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink/50">
          {t('Tutar (TL)', 'Amount (TL)')}
        </label>
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(Number(e.target.value))}
          className="w-full rounded-xl border border-ink/15 px-3 py-2.5 outline-none focus:ring-2 focus:ring-mint"
        />

        <button
          type="button"
          onClick={() =>
            send({
              supplier,
              product: 'bardak',
              quantity: 500,
              amount: Number(amount) || 0,
            })
          }
          className="w-full rounded-xl bg-ink py-3 text-sm font-semibold text-mint"
        >
          {t('Faturayı Gönder (Süreci Tetikle)', 'Send Invoice (Trigger Process)')}
        </button>

        <button
          type="button"
          onClick={() =>
            send({
              supplier,
              product: 'bardak',
              quantity: 500,
              amount: SUSPICIOUS_AMOUNT,
              force_anomaly: true,
            })
          }
          className="w-full rounded-xl border border-danger/40 py-3 text-sm font-semibold text-danger hover:bg-danger/10"
        >
          {t('Şüpheli / Limit Üstü Fatura Gönder', 'Send Suspicious / Over Limit Invoice')}
        </button>
      </div>

      <div className="space-y-4 rounded-2xl border border-ink/10 bg-white/70 p-6">
        <h2 className="text-sm font-bold uppercase tracking-wide text-ink/70">
          {t('B2C: Müşteri İade Akışı', 'B2C: Customer Return Flow')}
        </h2>
        <input
          type="text"
          value={returnText}
          onChange={(e) => setReturnText(e.target.value)}
          placeholder={t('İade edilecek ürünü ve fiyatını yazın. Örn: Siyah Deri Ceket, 5000 TL', 'Type the product to return and its price. e.g.: Black Leather Jacket, 5000 TL')}
          className="w-full rounded-xl border border-ink/15 px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-mint"
        />
        <button
          type="button"
          onClick={sendReturn}
          className="w-full rounded-xl border border-ink/20 bg-sand/50 py-3 text-sm font-semibold text-ink hover:bg-sand"
        >
          {t('Müşteri İadesi (B2C Modülü)', 'Customer Return (B2C Module)')}
        </button>
        {status && <p className="font-mono text-xs text-mint-dim">{status}</p>}
      </div>
    </div>
  )
}
