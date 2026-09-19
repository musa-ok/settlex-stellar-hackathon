import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../hooks/useLanguage.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'
import { walletErrorText } from '../wallet'

function short(pk) {
  return pk ? `${pk.slice(0, 6)}…${pk.slice(-4)}` : ''
}

function Step({ n, title, done, children }) {
  return (
    <li className="card-inset flex flex-col gap-3 p-4 sm:p-5">
      <div className="flex items-center gap-3">
        <span
          className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${
            done ? 'bg-mint-dim text-white' : 'bg-ink/10 text-ink/60'
          }`}
        >
          {done ? '✓' : n}
        </span>
        <h3 className="text-sm font-bold text-ink sm:text-base">{title}</h3>
      </div>
      {children}
    </li>
  )
}

// Company wallet (Stellar Wallets Kit) → SEP-10 with the TRY anchor → fund the AI agent.
export default function WalletPanel({ wallet }) {
  const { t } = useLanguage()
  const auth = useAuth()
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [balance, setBalance] = useState(null)
  const [agent, setAgent] = useState(null)
  const [agentBalance, setAgentBalance] = useState(null)
  const [anchorDomain, setAnchorDomain] = useState('')
  const [amount, setAmount] = useState(50)
  const [asset, setAsset] = useState('XLM')
  const [funded, setFunded] = useState(null)

  async function refreshBalances(pk = wallet.address, agentPk = agent) {
    if (pk) api.balance(pk).then(setBalance).catch(() => setBalance(null))
    if (agentPk) api.balance(agentPk).then(setAgentBalance).catch(() => {})
  }

  useEffect(() => {
    api.walletAgent()
      .then((a) => {
        setAgent(a.public_key)
        api.balance(a.public_key).then(setAgentBalance).catch(() => {})
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    setBalance(null)
    if (wallet.address) api.balance(wallet.address).then(setBalance).catch(() => {})
  }, [wallet.address])

  async function run(step, fn) {
    setBusy(step)
    setError('')
    try {
      await fn()
    } catch (err) {
      setError(walletErrorText(err) || t('İşlem başarısız', 'Action failed'))
    } finally {
      setBusy('')
    }
  }

  const connected = Boolean(wallet.address)

  return (
    <section className="card p-4 sm:p-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow" lang="en">Stellar Wallets Kit · SEP-10</p>
          <h2 className="mt-1 text-xl font-bold text-ink sm:text-2xl">{t('Şirket Cüzdanı', 'Company Wallet')}</h2>
          <p className="mt-1 text-sm text-ink/55">
            {t(
              'Freighter (veya xBull, Albedo, Lobstr) bağla, TRY anchor ile doğrula, ajana bütçe yükle.',
              'Connect Freighter (or xBull, Albedo, Lobstr), verify with the TRY anchor, fund the agent.',
            )}
          </p>
        </div>
        <span className="chip w-fit bg-ink/5 font-mono normal-case tracking-normal text-ink/55">Testnet</span>
      </div>

      <ol className="mt-5 grid gap-3 lg:grid-cols-3">
        <Step n={1} title={t('Cüzdanı bağla', 'Connect wallet')} done={connected}>
          {connected ? (
            <>
              <p className="break-all font-mono text-xs text-ink/70">{wallet.address}</p>
              {balance && (
                <p className="text-sm font-semibold tabular-nums text-ink">
                  {Number(balance.xlm).toFixed(2)} XLM · {Number(balance.usdc).toFixed(2)} USDC
                </p>
              )}
              <div className="mt-auto grid grid-cols-2 gap-2">
                <button type="button" disabled={Boolean(busy)} onClick={() => run('connect', wallet.connect)} className="btn btn-ghost px-3">
                  {t('Değiştir', 'Switch')}
                </button>
                <button type="button" disabled={Boolean(busy)} onClick={() => run('connect', wallet.disconnect)} className="btn btn-ghost px-3 text-danger">
                  {t('Bağlantıyı kes', 'Disconnect')}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-ink/55">
                {t('Freighter eklentisinde ağı Testnet seçin.', 'Set the network to Testnet in Freighter.')}
              </p>
              <button type="button" disabled={Boolean(busy)} onClick={() => run('connect', wallet.connect)} className="btn btn-primary mt-auto w-full">
                {busy === 'connect' ? t('Cüzdan bekleniyor…', 'Waiting for wallet…') : t('Cüzdan Bağla', 'Connect Wallet')}
              </button>
            </>
          )}
        </Step>

        <Step n={2} title={t('TRY anchor ile doğrula', 'Verify with TRY anchor')} done={wallet.anchorVerified}>
          <p className="text-sm text-ink/55">
            {wallet.anchorVerified
              ? t(`Cüzdan ${anchorDomain || 'anchor'} ile SEP-10 doğrulandı.`, `Wallet verified with ${anchorDomain || 'the anchor'} via SEP-10.`)
              : t('Anchor bir giriş işlemi gönderir, cüzdanınızda imzalarsınız — şifre veya API anahtarı yok.', 'The anchor sends a login challenge you sign in your wallet — no password or API key.')}
          </p>
          <button
            type="button"
            disabled={!connected || Boolean(busy)}
            onClick={() => run('anchor', async () => setAnchorDomain((await wallet.verifyAnchor()).home_domain))}
            className={`btn mt-auto w-full ${wallet.anchorVerified ? 'btn-ghost' : 'btn-primary'}`}
          >
            {busy === 'anchor'
              ? t('Cüzdanda imza bekleniyor…', 'Waiting for wallet signature…')
              : wallet.anchorVerified
                ? t('Tekrar doğrula', 'Verify again')
                : t('Anchor ile Doğrula (SEP-10)', 'Verify with Anchor (SEP-10)')}
          </button>
        </Step>

        <Step n={3} title={t('Ajana bütçe yükle', 'Fund the AI agent')} done={Boolean(funded)}>
          <p className="text-sm text-ink/55">
            {t('Ajan pazarlıkları bu cüzdandan öder.', 'The agent settles deals from this wallet.')}{' '}
            {agent && <span className="font-mono text-xs text-ink/70">{short(agent)}</span>}
            {agentBalance && (
              <span className="font-semibold tabular-nums text-ink"> · {Number(agentBalance.xlm).toFixed(0)} XLM</span>
            )}
          </p>
          <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
            <input
              type="number"
              min="1"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="field tabular-nums"
              aria-label={t('Tutar', 'Amount')}
            />
            <div className="flex rounded-2xl bg-ink/5 p-1">
              {['XLM', 'USDC'].map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => setAsset(a)}
                  className={`min-h-10 rounded-xl px-3 text-xs font-bold transition ${asset === a ? 'bg-white text-ink shadow-sm' : 'text-ink/50'}`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            disabled={!connected || !auth.authenticated || !(Number(amount) > 0) || Boolean(busy)}
            onClick={() =>
              run('fund', async () => {
                const res = await wallet.fundAgent(Number(amount), asset)
                setFunded(res)
                await refreshBalances()
              })
            }
            className="btn btn-mint w-full"
          >
            {busy === 'fund'
              ? t('Cüzdanda imza bekleniyor…', 'Waiting for wallet signature…')
              : t(`${amount || 0} ${asset} Yükle`, `Send ${amount || 0} ${asset}`)}
          </button>
          {!auth.authenticated && connected && (
            <p className="text-xs text-ink/50">{t('Önce Passkey ile giriş yapın.', 'Log in with Passkey first.')}</p>
          )}
          {funded && (
            <a href={funded.explorer_url} target="_blank" rel="noreferrer" className="break-all rounded-xl bg-mint/10 px-3 py-2 font-mono text-xs text-mint-dim underline underline-offset-2">
              {funded.amount} {funded.asset} → {t('ajan', 'agent')} · Stellar Expert ↗
            </a>
          )}
        </Step>
      </ol>

      {error && <p className="mt-4 break-words rounded-2xl bg-red-50 px-4 py-3 font-mono text-xs text-red-700">{error}</p>}
    </section>
  )
}
