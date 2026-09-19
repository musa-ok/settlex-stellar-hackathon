import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useToast } from '../contexts/ToastContext'

export default function Balance() {
  const { t } = useLanguage()
  const { error, success } = useToast()
  const [bal, setBal] = useState(null)
  const [txs, setTxs] = useState([])
  const [sessions, setSessions] = useState([])
  const [iban, setIban] = useState('TR33 0006 1005 1978 6457 8413 26')
  const [amount, setAmount] = useState(445)
  const [result, setResult] = useState(null)
  const [isWithdrawing, setIsWithdrawing] = useState(false)
  const [validationError, setValidationError] = useState('')
  const wallet = localStorage.getItem('kasa_wallet')

  async function refresh() {
    const [b, t, s] = await Promise.all([
      api.balance(wallet || undefined),
      api.transactions(),
      api.sessions().catch(() => []),
    ])
    setBal(b)
    setTxs(t)
    setSessions(Array.isArray(s) ? s : [])
  }

  useEffect(() => {
    refresh().catch(console.error)
  }, [])

  function validateInputs() {
    // Validate IBAN format (TR + 24 digits)
    const cleanIban = iban.replace(/\s/g, '')
    const ibanRegex = /^TR\d{24}$/
    if (!ibanRegex.test(cleanIban)) {
      setValidationError(t('Geçersiz IBAN formatı (TRXX...)', 'Invalid IBAN format (TRXX...)'))
      return false
    }

    // Validate minimum 1 USDC
    if (Number(amount) < 1) {
      setValidationError(t('Minimum çekim tutarı 1 USDC', 'Minimum withdrawal amount is 1 USDC'))
      return false
    }

    // Validate maximum reasonable amount
    if (Number(amount) > 10000) {
      setValidationError(t('Maksimum çekim tutarı 10,000 USDC', 'Maximum withdrawal amount is 10,000 USDC'))
      return false
    }

    setValidationError('')
    return true
  }

  async function withdraw(e) {
    e.preventDefault()
    
    if (!validateInputs()) {
      error(validationError)
      return
    }

    setIsWithdrawing(true)
    try {
      const cleanIban = iban.replace(/\s/g, '')
      const res = await api.withdraw({ amount: Number(amount), iban: cleanIban })
      setResult(res)
      await refresh()
      
      if (res.ok) {
        success(t('Çekim işlemi başarılı!', 'Withdrawal successful!'))
      } else {
        error(res.message || t('Çekim işlemi başarısız', 'Withdrawal failed'))
      }
    } catch (err) {
      console.error('Withdraw error:', err)
      let errorMessage = t('Çekim işlemi başarısız', 'Withdrawal failed')
      
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
      
      error(errorMessage)
    } finally {
      setIsWithdrawing(false)
    }
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      <header>
        <p className="eyebrow">SEP-10 · SEP-6 · Stellar</p>
        <h1 className="mt-1 text-3xl font-bold text-ink sm:text-4xl">{t('Bakiye & Anchor', 'Balance & Anchor')}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink/60 sm:text-base">
          {t('Mutabakat sonrası ajan cüzdanı SEP-10 ile doğrulanır, SEP-6 ile TR IBAN\'a çekim açılır, USDC on-chain gider.', 'After settlement, the agent wallet is verified via SEP-10, withdrawal to TR IBAN is opened via SEP-6, and USDC is transferred on-chain.')}
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-3 sm:gap-4">
        {[
          { label: 'XLM', value: bal?.xlm },
          { label: 'USDC', value: bal?.usdc },
          { label: t('Çekilebilir TRY', 'Withdrawable TRY'), value: bal?.mock_try },
        ].map((c) => (
          <div key={c.label} className="card flex items-baseline justify-between gap-3 px-5 py-4 sm:block sm:p-6">
            <p className="eyebrow">{c.label}</p>
            <p className="font-display text-2xl font-bold tabular-nums tracking-tight text-ink sm:mt-3 sm:text-3xl">
              {c.value != null ? Number(c.value).toFixed(2) : '—'}
            </p>
          </div>
        ))}
      </div>

      {bal?.public_key && (
        <p className="break-all rounded-2xl bg-white/60 px-4 py-3 font-mono text-xs text-ink/50 ring-1 ring-ink/[0.05]">{bal.public_key}</p>
      )}

      <form
        onSubmit={withdraw}
        className="relative overflow-hidden rounded-3xl bg-ink p-5 text-sand shadow-[var(--shadow-lift)] sm:p-7 md:max-w-lg"
      >
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-mint/15 blur-3xl" />
        <h2 className="relative text-xl font-bold text-mint sm:text-2xl">{t('Bankaya çek', 'Withdraw to bank')}</h2>
        <p className="relative mt-1 text-sm text-sand/55">SEP-1 dynamic discovery · SEP-6 · SEP-10 ({t('API key yok', 'No API key')})</p>
        <label className="relative mt-5 mb-1.5 block text-xs font-semibold uppercase tracking-[0.08em] text-sand/55">{t('Tutar (TL)', 'Amount (TL)')}</label>
        <input
          type="number"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="relative min-h-12 w-full rounded-2xl border border-sand/15 bg-panel px-4 py-3 text-base tabular-nums text-sand outline-none transition focus:border-mint focus:ring-4 focus:ring-mint/15 sm:text-sm"
        />
        <label className="relative mt-4 mb-1.5 block text-xs font-semibold uppercase tracking-[0.08em] text-sand/55">IBAN (mock)</label>
        <input
          value={iban}
          onChange={(e) => setIban(e.target.value)}
          className="relative min-h-12 w-full rounded-2xl border border-sand/15 bg-panel px-4 py-3 font-mono text-base text-sand outline-none transition focus:border-mint focus:ring-4 focus:ring-mint/15 sm:text-sm"
        />
        <button
          type="submit"
          disabled={isWithdrawing}
          className="btn btn-mint relative mt-6 w-full font-bold"
        >
          {isWithdrawing ? t('İşleniyor...', 'Processing...') : t('Bankaya Çek', 'Withdraw to Bank')}
        </button>
        {validationError && (
          <p className="relative mt-4 break-words font-mono text-xs text-red-400">{validationError}</p>
        )}
        {result && (
          <p className={`relative mt-4 break-all font-mono text-xs ${result.ok ? 'text-mint' : 'text-red-400'}`}>
            {result.message}
          </p>
        )}
        {result?.fiat && (
          <div className="relative mt-3 rounded-2xl bg-mint/10 px-4 py-3 ring-1 ring-mint/25">
            <p className="font-display text-lg font-bold tabular-nums text-mint">
              {result.fiat.amount_out} {result.fiat.currency} · {result.fiat.status}
            </p>
            {result.fiat.message && <p className="mt-1 break-words text-xs text-sand/70">{result.fiat.message}</p>}
          </div>
        )}
      </form>

      <div>
        <h2 className="mb-3 text-lg font-bold text-ink">{t('On-chain mutabakatlar', 'On-chain settlements')}</h2>
        <div className="card overflow-hidden">
          <table className="block w-full text-left text-sm sm:table">
            <thead className="hidden border-b border-ink/[0.06] bg-sand/40 font-mono text-[11px] uppercase tracking-wider text-ink/45 sm:table-header-group">
              <tr>
                <th className="px-5 py-3 font-semibold">{t('Tedarikçi', 'Supplier')}</th>
                <th className="px-5 py-3 font-semibold">{t('Tutar', 'Amount')}</th>
                <th className="px-5 py-3 font-semibold">tx_hash</th>
              </tr>
            </thead>
            <tbody className="block divide-y divide-ink/[0.05] sm:table-row-group">
              {sessions.length === 0 && (
                <tr className="block sm:table-row">
                  <td colSpan={3} className="block px-5 py-8 text-center text-ink/40 sm:table-cell">
                    {t('Henüz kayıtlı mutabakat yok', 'No persisted settlements yet')}
                  </td>
                </tr>
              )}
              {sessions.map((s) => (
                <tr key={s.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 px-4 py-4 transition hover:bg-sand/30 sm:table-row sm:p-0">
                  <td className="min-w-0 truncate font-medium sm:px-5 sm:py-3.5">{s.supplier}</td>
                  <td className="text-right font-semibold tabular-nums sm:px-5 sm:py-3.5 sm:text-left">{Number(s.amount).toFixed(2)}</td>
                  <td className="col-span-2 min-w-0 sm:px-5 sm:py-3.5">
                    {s.explorer_url ? (
                      <a
                        className="block break-all font-mono text-xs text-mint-dim underline decoration-mint/40 underline-offset-2"
                        href={s.explorer_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.tx_hash}
                      </a>
                    ) : (
                      <span className="text-ink/35">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-bold text-ink">{t('İşlem geçmişi', 'Transaction history')}</h2>
        <div className="card overflow-hidden">
          <table className="block w-full text-left text-sm sm:table">
            <thead className="hidden border-b border-ink/[0.06] bg-sand/40 font-mono text-[11px] uppercase tracking-wider text-ink/45 sm:table-header-group">
              <tr>
                <th className="px-5 py-3 font-semibold">{t('Tarih', 'Date')}</th>
                <th className="px-5 py-3 font-semibold">{t('Tedarikçi', 'Supplier')}</th>
                <th className="px-5 py-3 font-semibold">{t('Tutar', 'Amount')}</th>
                <th className="px-5 py-3 font-semibold">{t('Durum', 'Status')}</th>
              </tr>
            </thead>
            <tbody className="block divide-y divide-ink/[0.05] sm:table-row-group">
              {txs.length === 0 && (
                <tr className="block sm:table-row">
                  <td colSpan={4} className="block px-5 py-8 text-center text-ink/40 sm:table-cell">
                    {t('Henüz işlem yok', 'No transactions yet')}
                  </td>
                </tr>
              )}
              {txs.map((t) => (
                <tr key={t.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 px-4 py-4 transition hover:bg-sand/30 sm:table-row sm:p-0">
                  <td className="col-span-2 font-mono text-xs text-ink/50 sm:px-5 sm:py-3.5">
                    {new Date(t.created_at).toLocaleString('tr-TR')}
                  </td>
                  <td className="min-w-0 truncate font-medium sm:px-5 sm:py-3.5">{t.supplier}</td>
                  <td className="text-right font-semibold tabular-nums sm:px-5 sm:py-3.5 sm:text-left">{t.amount.toFixed(2)} {t.asset}</td>
                  <td className="col-span-2 sm:px-5 sm:py-3.5">
                    <span className="chip bg-mint/15 font-mono normal-case tracking-normal text-mint-dim">{t.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
