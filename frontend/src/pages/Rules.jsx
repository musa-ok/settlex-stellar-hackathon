import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage.jsx'

export default function Rules() {
  const { t } = useLanguage()
  const [rules, setRules] = useState([])
  const [text, setText] = useState(
    t("Kağıt Tedarik A.Ş.'den bardak alımlarında bütçe max 450 TL, otomatik öde.", "Budget max 450 TL for cup purchases from Paper Supply Inc., pay automatically.")
  )
  const [form, setForm] = useState({ supplier: '', budget_limit: 450, anomaly_threshold: 900 })
  const [msg, setMsg] = useState('')

  async function refresh() {
    setRules(await api.listRules())
  }

  useEffect(() => {
    refresh().catch(console.error)
  }, [])

  async function fromNaturalLanguage(e) {
    e.preventDefault()
    setMsg(t('Kural ayrıştırılıyor…', 'Parsing rule…'))
    const parsed = await api.parseRule(text)
    const rule = await api.createRule(parsed)
    setMsg(t(`Eklendi: ${rule.supplier} · max ${rule.budget_limit} TL`, `Added: ${rule.supplier} · max ${rule.budget_limit} TL`))
    setText('')
    await refresh()
  }

  async function fromForm(e) {
    e.preventDefault()
    await api.createRule({
      ...form,
      budget_limit: Number(form.budget_limit),
      anomaly_threshold: Number(form.anomaly_threshold),
      raw_text: `${form.supplier} max ${form.budget_limit} TL`,
    })
    setMsg(t('Form kuralı kaydedildi', 'Form rule saved'))
    setForm({ supplier: '', budget_limit: 450, anomaly_threshold: 900 })
    await refresh()
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="animate-fade-up max-w-2xl">
        <p className="eyebrow">RuleEngine</p>
        <h1 className="mt-1 text-3xl font-bold text-ink sm:text-4xl">{t('Kurallar', 'Rules')}</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink/60 sm:text-base">
          {t('RuleEngine: doğal dille veya formla kural koy — ajan faturaları buna göre onaylar veya pazarlık eder.', 'RuleEngine: set rules via natural language or form — agents approve or negotiate invoices accordingly.')}
        </p>
      </header>

      <form
        onSubmit={fromNaturalLanguage}
        className="card animate-fade-up p-4 sm:p-6"
      >
        <label className="field-label">{t('Doğal dil', 'Natural language')}</label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="field resize-y leading-relaxed"
          placeholder={t('Örn: "OfisMarket Ltd. için max 300 TL öde"', 'e.g.: "Pay max 300 TL for OfficeMarket Ltd."')}
        />
        <button
          type="submit"
          className="btn btn-primary mt-4 w-full sm:w-auto"
        >
          {t('Kuralı kaydet', 'Save rule')}
        </button>
      </form>

      <form
        onSubmit={fromForm}
        className="card grid gap-3 p-4 sm:p-6 md:grid-cols-3"
      >
        <div className="md:col-span-3">
          <h2 className="text-base font-bold text-ink">{t('veya form ile', 'or via form')}</h2>
        </div>
        <input
          required
          placeholder={t('Tedarikçi', 'Supplier')}
          value={form.supplier}
          onChange={(e) => setForm({ ...form, supplier: e.target.value })}
          className="field"
        />
        <input
          type="number"
          required
          placeholder={t('Bütçe limiti (TL)', 'Budget limit (TL)')}
          value={form.budget_limit}
          onChange={(e) => setForm({ ...form, budget_limit: e.target.value })}
          className="field"
        />
        <input
          type="number"
          placeholder={t('Anomali eşiği', 'Anomaly threshold')}
          value={form.anomaly_threshold}
          onChange={(e) => setForm({ ...form, anomaly_threshold: e.target.value })}
          className="field"
        />
        <button
          type="submit"
          className="btn btn-ghost w-full md:col-span-3 md:w-fit"
        >
          {t('Formdan ekle', 'Add from form')}
        </button>
      </form>

      {msg && <p className="break-words rounded-2xl bg-mint/10 px-4 py-3 font-mono text-sm text-mint-dim">{msg}</p>}

      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        {rules.map((r) => (
          <article
            key={r.id}
            className="relative flex flex-col overflow-hidden rounded-3xl bg-ink p-5 text-sand shadow-[var(--shadow-soft)] sm:p-6"
          >
            <h3 className="break-words text-lg font-bold text-mint sm:text-xl">{r.supplier}</h3>
            <dl className="mt-3 space-y-1.5 font-mono text-xs text-sand/70">
              <div>{t('bütçe', 'budget')} ≤ {r.budget_limit.toFixed(2)} TL</div>
              <div>{t('anomali', 'anomaly')} &gt; {r.anomaly_threshold.toFixed(2)} TL</div>
              {r.product_hint && <div>{t('ürün', 'product')}: {r.product_hint}</div>}
            </dl>
            {r.raw_text && (
              <p className="mt-4 break-words border-t border-sand/10 pt-3 text-sm leading-relaxed text-sand/55">{r.raw_text}</p>
            )}
            <button
              type="button"
              onClick={async () => {
                await api.deleteRule(r.id)
                await refresh()
              }}
              className="mt-4 inline-flex min-h-10 w-fit items-center rounded-xl px-3 text-xs font-semibold text-danger ring-1 ring-danger/30 transition hover:bg-danger/10"
            >
              {t('Sil', 'Delete')}
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}
