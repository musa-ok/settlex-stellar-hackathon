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
    <div className="space-y-10">
      <header className="animate-fade-up max-w-2xl">
        <h1 className="font-display text-4xl font-bold text-ink">{t('Kurallar', 'Rules')}</h1>
        <p className="mt-2 text-ink/60">
          {t('RuleEngine: doğal dille veya formla kural koy — ajan faturaları buna göre onaylar veya pazarlık eder.', 'RuleEngine: set rules via natural language or form — agents approve or negotiate invoices accordingly.')}
        </p>
      </header>

      <form
        onSubmit={fromNaturalLanguage}
        className="animate-fade-up rounded-2xl border border-ink/10 bg-white/70 p-6 shadow-sm backdrop-blur"
      >
        <label className="block text-sm font-semibold text-ink">{t('Doğal dil', 'Natural language')}</label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="mt-2 w-full resize-y rounded-xl border border-ink/15 bg-sand/50 px-4 py-3 text-ink outline-none ring-mint focus:ring-2"
          placeholder={t('Örn: "OfisMarket Ltd. için max 300 TL öde"', 'e.g.: "Pay max 300 TL for OfficeMarket Ltd."')}
        />
        <button
          type="submit"
          className="mt-4 rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-mint transition hover:bg-ink-soft"
        >
          {t('Kuralı kaydet', 'Save rule')}
        </button>
      </form>

      <form
        onSubmit={fromForm}
        className="grid gap-4 rounded-2xl border border-ink/10 bg-white/50 p-6 md:grid-cols-3"
      >
        <div className="md:col-span-3">
          <h2 className="text-sm font-semibold text-ink">{t('veya form ile', 'or via form')}</h2>
        </div>
        <input
          required
          placeholder={t('Tedarikçi', 'Supplier')}
          value={form.supplier}
          onChange={(e) => setForm({ ...form, supplier: e.target.value })}
          className="rounded-xl border border-ink/15 bg-white px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-mint"
        />
        <input
          type="number"
          required
          placeholder={t('Bütçe limiti (TL)', 'Budget limit (TL)')}
          value={form.budget_limit}
          onChange={(e) => setForm({ ...form, budget_limit: e.target.value })}
          className="rounded-xl border border-ink/15 bg-white px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-mint"
        />
        <input
          type="number"
          placeholder={t('Anomali eşiği', 'Anomaly threshold')}
          value={form.anomaly_threshold}
          onChange={(e) => setForm({ ...form, anomaly_threshold: e.target.value })}
          className="rounded-xl border border-ink/15 bg-white px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-mint"
        />
        <button
          type="submit"
          className="rounded-xl border border-ink/20 px-4 py-2.5 text-sm font-semibold text-ink hover:bg-ink hover:text-mint md:col-span-3 md:w-fit"
        >
          {t('Formdan ekle', 'Add from form')}
        </button>
      </form>

      {msg && <p className="font-mono text-sm text-mint-dim">{msg}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        {rules.map((r) => (
          <article
            key={r.id}
            className="rounded-2xl border border-ink/10 bg-ink p-5 text-sand"
          >
            <h3 className="font-display text-xl font-semibold text-mint">{r.supplier}</h3>
            <dl className="mt-3 space-y-1 font-mono text-xs text-sand/70">
              <div>{t('bütçe', 'budget')} ≤ {r.budget_limit.toFixed(2)} TL</div>
              <div>{t('anomali', 'anomaly')} &gt; {r.anomaly_threshold.toFixed(2)} TL</div>
              {r.product_hint && <div>{t('ürün', 'product')}: {r.product_hint}</div>}
            </dl>
            {r.raw_text && (
              <p className="mt-3 border-t border-sand/10 pt-3 text-sm text-sand/55">{r.raw_text}</p>
            )}
            <button
              type="button"
              onClick={async () => {
                await api.deleteRule(r.id)
                await refresh()
              }}
              className="mt-4 text-xs text-danger hover:underline"
            >
              {t('Sil', 'Delete')}
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}
