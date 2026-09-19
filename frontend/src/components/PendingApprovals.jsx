import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

const PENDING = {
  PENDING_APPROVAL: 'purchase',
  PENDING_INSPECTION: 'refund',
}

// Backend errors arrive as JSON text: {"detail": {"error", "message"}}.
function errorText(err) {
  try {
    const { detail } = JSON.parse(err.message)
    return [detail.error, detail.message].filter(Boolean).join(' — ')
  } catch {
    return err.message
  }
}

// Lists payments held by the B2B security layer and lets a human release or cancel them:
// purchases wait for a manager (maker-checker), refunds wait for the returned parcel (escrow).
export default function PendingApprovals({ flow, refreshKey }) {
  const { t, language } = useLanguage()
  const auth = useAuth()
  const [items, setItems] = useState([])
  const [working, setWorking] = useState(null) // { id, action: 'sign' | 'approve' | 'reject' }
  const [error, setError] = useState('')

  async function refresh() {
    const list = await api.listNegotiations()
    if (!Array.isArray(list)) return
    setItems(list.filter((n) => PENDING[n.status] && (!flow || PENDING[n.status] === flow)))
  }

  useEffect(() => {
    refresh().catch(() => {})
  }, [refreshKey, flow])

  async function approve(n) {
    setError('')
    try {
      // Physical confirmation at signing time: FaceID / TouchID before any funds move.
      setWorking({ id: n.id, action: 'sign' })
      const stepUpToken = await auth.confirmWithPasskey()
      setWorking({ id: n.id, action: 'approve' })
      if (n.status === 'PENDING_INSPECTION') {
        await api.approveReturn(n.id, language, stepUpToken)
      } else {
        await api.approvePurchase(n.id, language, stepUpToken)
      }
    } catch (err) {
      setError(errorText(err) || t('Onay başarısız', 'Approval failed'))
    } finally {
      setWorking(null)
      refresh().catch(() => {})
    }
  }

  async function reject(n) {
    setError('')
    setWorking({ id: n.id, action: 'reject' })
    try {
      if (n.status === 'PENDING_INSPECTION') {
        await api.rejectReturn(n.id, language)
      } else {
        await api.rejectPurchase(n.id, language)
      }
    } catch (err) {
      setError(errorText(err) || t('Reddetme başarısız', 'Rejection failed'))
    } finally {
      setWorking(null)
      refresh().catch(() => {})
    }
  }

  if (items.length === 0) return null

  return (
    <section className="card overflow-hidden">
      <div className="flex items-start gap-3 border-b border-ink/[0.06] bg-gradient-to-r from-orange-50 to-amber-50/40 px-4 py-4 sm:px-6">
        <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-orange-500/15 text-orange-600">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4z" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold text-ink sm:text-xl">
              {t('Onay Bekleyen Ödemeler', 'Payments Awaiting Approval')}
            </h2>
            <span className="chip bg-orange-500 text-white">{items.length}</span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink/60">
            {t(
              'Ajanlar anlaştı; para, bir insan onaylayana kadar Stellar\'a gönderilmez.',
              'The agents agreed; no funds move on Stellar until a human approves.',
            )}
          </p>
        </div>
      </div>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))] gap-3 p-3 sm:p-4">
        {items.map((n) => {
          const isRefund = n.status === 'PENDING_INSPECTION'
          const action = working?.id === n.id ? working.action : null
          return (
            <li
              key={n.id}
              className="flex flex-col rounded-2xl border border-ink/[0.07] bg-white p-4 shadow-sm transition hover:shadow-md sm:p-5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={`chip ${isRefund ? 'bg-sky-100 text-sky-800' : 'bg-violet-100 text-violet-800'}`}>
                  {isRefund ? t('İade', 'Refund') : t('Satın Alma', 'Purchase')}
                </span>
                <span className="chip bg-orange-100 text-orange-800 normal-case tracking-normal">
                  <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-orange-500" />
                  {isRefund
                    ? t('Kargo Bekleniyor', 'Awaiting Return Shipment')
                    : t('Yönetici Onayı Bekliyor', 'Awaiting Manager Approval')}
                </span>
              </div>

              <p className="mt-4 font-display text-3xl font-bold tabular-nums tracking-tight text-ink">
                {Number(n.agreed_amount ?? n.current_amount).toFixed(2)}
                <span className="ml-1.5 text-base font-semibold text-ink/40">TL</span>
              </p>
              <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-ink/45">{isRefund ? t('Mağaza', 'Store') : t('Tedarikçi', 'Supplier')}</dt>
                <dd className="truncate font-medium text-ink">{n.supplier}</dd>
                <dt className="text-ink/45">{t('Ürün', 'Product')}</dt>
                <dd className="truncate font-medium text-ink">{n.product}</dd>
              </dl>

              <div className="mt-5 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                <button
                  type="button"
                  disabled={working !== null}
                  onClick={() => approve(n)}
                  className="btn bg-emerald-600 px-3 text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500 sm:px-4"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <path d="M7 11a5 5 0 0 1 10 0v2a9 9 0 0 1-1 4M12 11v3a7 7 0 0 1-2 5M4 13v-2a8 8 0 0 1 14-5.3M20 11v1" />
                  </svg>
                  <span>
                    {action === 'sign'
                      ? t('Biyometrik onay bekleniyor…', 'Waiting for biometric confirmation…')
                      : action === 'approve'
                        ? t('Stellar ödemesi gönderiliyor…', 'Sending Stellar payment…')
                        : isRefund
                          ? t('Kargoyu Onayla ve İadeyi Tamamla', 'Approve Return')
                          : t('Satın Almayı Onayla (Yönetici)', 'Approve Purchase (Manager)')}
                  </span>
                </button>
                <button
                  type="button"
                  disabled={working !== null}
                  onClick={() => reject(n)}
                  className="btn border border-red-200 bg-red-50 px-3 text-red-700 hover:border-red-300 hover:bg-red-100 sm:px-4"
                >
                  {action === 'reject' ? t('İptal ediliyor…', 'Cancelling…') : t('İptal Et / Reddet', 'Cancel / Reject')}
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      {error && (
        <p className="mx-3 mb-3 break-words rounded-2xl bg-red-50 px-4 py-3 font-mono text-xs text-red-700 sm:mx-4 sm:mb-4">
          {error}
        </p>
      )}
    </section>
  )
}
