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
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-4xl font-bold text-ink">{t('Bakiye & Anchor', 'Balance & Anchor')}</h1>
        <p className="mt-2 text-ink/60">
          {t('Mutabakat sonrası ajan cüzdanı SEP-10 ile doğrulanır, SEP-6 ile TR IBAN\'a çekim açılır, USDC on-chain gider.', 'After settlement, the agent wallet is verified via SEP-10, withdrawal to TR IBAN is opened via SEP-6, and USDC is transferred on-chain.')}
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: 'XLM', value: bal?.xlm },
          { label: 'USDC', value: bal?.usdc },
          { label: t('Çekilebilir TRY', 'Withdrawable TRY'), value: bal?.mock_try },
        ].map((c) => (
          <div key={c.label} className="rounded-2xl border border-ink/10 bg-white/70 p-5">
            <p className="font-mono text-xs uppercase tracking-wider text-ink/45">{c.label}</p>
            <p className="mt-2 font-display text-3xl font-bold text-ink">
              {c.value != null ? Number(c.value).toFixed(2) : '—'}
            </p>
          </div>
        ))}
      </div>

      {bal?.public_key && (
        <p className="break-all font-mono text-xs text-ink/45">{bal.public_key}</p>
      )}

      <form
        onSubmit={withdraw}
        className="rounded-2xl bg-ink p-6 text-sand md:max-w-lg"
      >
        <h2 className="font-display text-2xl font-semibold text-mint">{t('Bankaya çek', 'Withdraw to bank')}</h2>
        <p className="mt-1 text-sm text-sand/55">SEP-1 dynamic discovery · SEP-6 · SEP-10 ({t('API key yok', 'No API key')})</p>
        <label className="mt-5 block text-xs font-medium text-sand/60">{t('Tutar (TL)', 'Amount (TL)')}</label>
        <input
          type="number"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="mt-1 w-full rounded-xl border border-sand/20 bg-panel px-3 py-2.5 text-sand outline-none focus:border-mint"
        />
        <label className="mt-4 block text-xs font-medium text-sand/60">IBAN (mock)</label>
        <input
          value={iban}
          onChange={(e) => setIban(e.target.value)}
          className="mt-1 w-full rounded-xl border border-sand/20 bg-panel px-3 py-2.5 font-mono text-sm text-sand outline-none focus:border-mint"
        />
        <button
          type="submit"
          disabled={isWithdrawing}
          className="mt-5 w-full rounded-xl bg-mint py-3 text-sm font-bold text-ink hover:bg-white disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isWithdrawing ? t('İşleniyor...', 'Processing...') : t('Bankaya Çek', 'Withdraw to Bank')}
        </button>
        {validationError && (
          <p className="mt-4 font-mono text-xs text-red-500">{validationError}</p>
        )}
        {result && (
          <p className={`mt-4 break-all font-mono text-xs ${result.ok ? 'text-mint' : 'text-red-500'}`}>
            {result.message}
          </p>
        )}
      </form>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-ink">{t('On-chain mutabakatlar', 'On-chain settlements')}</h2>
        <div className="overflow-x-auto rounded-2xl border border-ink/10 bg-white/60">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="border-b border-ink/10 font-mono text-xs uppercase text-ink/45">
              <tr>
                <th className="px-4 py-3">{t('Tedarikçi', 'Supplier')}</th>
                <th className="px-4 py-3">{t('Tutar', 'Amount')}</th>
                <th className="px-4 py-3">tx_hash</th>
              </tr>
            </thead>
            <tbody>
              {sessions.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-ink/40">
                    {t('Henüz kayıtlı mutabakat yok', 'No persisted settlements yet')}
                  </td>
                </tr>
              )}
              {sessions.map((s) => (
                <tr key={s.id} className="border-t border-ink/5">
                  <td className="px-4 py-3">{s.supplier}</td>
                  <td className="px-4 py-3 font-semibold">{Number(s.amount).toFixed(2)}</td>
                  <td className="px-4 py-3">
                    {s.explorer_url ? (
                      <a
                        className="break-all font-mono text-xs text-mint-dim underline"
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
        <h2 className="mb-3 text-sm font-semibold text-ink">{t('İşlem geçmişi', 'Transaction history')}</h2>
        <div className="overflow-x-auto rounded-2xl border border-ink/10 bg-white/60">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="border-b border-ink/10 font-mono text-xs uppercase text-ink/45">
              <tr>
                <th className="px-4 py-3">{t('Tarih', 'Date')}</th>
                <th className="px-4 py-3">{t('Tedarikçi', 'Supplier')}</th>
                <th className="px-4 py-3">{t('Tutar', 'Amount')}</th>
                <th className="px-4 py-3">{t('Durum', 'Status')}</th>
              </tr>
            </thead>
            <tbody>
              {txs.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-ink/40">
                    {t('Henüz işlem yok', 'No transactions yet')}
                  </td>
                </tr>
              )}
              {txs.map((t) => (
                <tr key={t.id} className="border-t border-ink/5">
                  <td className="px-4 py-3 font-mono text-xs">
                    {new Date(t.created_at).toLocaleString('tr-TR')}
                  </td>
                  <td className="px-4 py-3">{t.supplier}</td>
                  <td className="px-4 py-3 font-semibold">{t.amount.toFixed(2)} {t.asset}</td>
                  <td className="px-4 py-3 text-mint-dim">{t.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
