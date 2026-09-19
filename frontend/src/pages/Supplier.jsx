import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage'
import PendingApprovals from '../components/PendingApprovals.jsx'

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
    <div className="mx-auto max-w-2xl space-y-6 sm:space-y-8">
      <header>
        <p className="eyebrow">{t('Tedarikçi', 'Supplier')}</p>
        <h1 className="mt-1 text-3xl font-bold text-ink sm:text-4xl">{t('Demo Simülasyon Paneli', 'Demo Simulation Panel')}</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink/60 sm:text-base">
          {t('B2B kurumsal fatura veya B2C müşteri iadesi — ajan pazarlığını tetikle.', 'B2B corporate invoice or B2C customer return — trigger agent negotiation.')}
        </p>
      </header>

      <div className="card space-y-4 p-4 sm:p-6">
        <div className="flex items-center gap-2">
          <span className="chip bg-violet-100 text-violet-800">B2B</span>
          <h2 className="text-sm font-bold text-ink">
            {t('B2B: Kurumsal Fatura Akışı', 'B2B: Corporate Invoice Flow')}
          </h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="min-w-0">
            <label className="field-label">
              {t('Tedarikçi', 'Supplier')}
            </label>
            <input
              value={supplier}
              onChange={(e) => setSupplier(e.target.value)}
              className="field"
            />
          </div>
          <div className="min-w-0">
            <label className="field-label">
              {t('Tutar (TL)', 'Amount (TL)')}
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="field tabular-nums"
            />
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
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
            className="btn btn-primary w-full"
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
            className="btn w-full border border-danger/30 bg-red-50 text-danger hover:bg-red-100"
          >
            {t('Şüpheli / Limit Üstü Fatura Gönder', 'Send Suspicious / Over Limit Invoice')}
          </button>
        </div>
      </div>

      <div className="card space-y-4 p-4 sm:p-6">
        <div className="flex items-center gap-2">
          <span className="chip bg-sky-100 text-sky-800">B2C</span>
          <h2 className="text-sm font-bold text-ink">
            {t('B2C: Müşteri İade Akışı', 'B2C: Customer Return Flow')}
          </h2>
        </div>
        <input
          type="text"
          value={returnText}
          onChange={(e) => setReturnText(e.target.value)}
          placeholder={t('İade edilecek ürünü ve fiyatını yazın. Örn: Siyah Deri Ceket, 5000 TL', 'Type the product to return and its price. e.g.: Black Leather Jacket, 5000 TL')}
          className="field"
        />
        <button
          type="button"
          onClick={sendReturn}
          className="btn btn-ghost w-full"
        >
          {t('Müşteri İadesi (B2C Modülü)', 'Customer Return (B2C Module)')}
        </button>
        {status && <p className="rounded-xl bg-mint/10 px-3 py-2 font-mono text-xs text-mint-dim">{status}</p>}
      </div>

      <PendingApprovals flow="refund" />
    </div>
  )
}
