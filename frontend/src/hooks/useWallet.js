import { useState } from 'react'
import { api } from '../api'
import { connectWallet, disconnectWallet, signWithWallet } from '../wallet'

const WALLET_KEY = 'kasa_wallet'
const ANCHOR_KEY = 'settlex_anchor_verified'

function read(key) {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

function write(key, value) {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    /* storage unavailable */
  }
}

// Company wallet connected through Stellar Wallets Kit (Freighter etc.).
export function useWallet() {
  const [address, setAddressState] = useState(() => read(WALLET_KEY))
  const [anchorVerified, setAnchorVerified] = useState(() => read(ANCHOR_KEY))

  function setAddress(pk) {
    write(WALLET_KEY, pk)
    setAddressState(pk)
    if (pk !== read(ANCHOR_KEY)) {
      write(ANCHOR_KEY, '')
      setAnchorVerified('')
    }
  }

  async function connect() {
    const pk = await connectWallet()
    setAddress(pk)
    await api.connectWallet(pk).catch(() => {})
    return pk
  }

  async function disconnect() {
    await disconnectWallet()
    setAddress('')
  }

  // SEP-10 with the TRY anchor, the challenge signed inside the user's wallet.
  async function verifyAnchor() {
    const challenge = await api.sep10Challenge(address)
    const signed = await signWithWallet(challenge.transaction, {
      address,
      networkPassphrase: challenge.network_passphrase,
    })
    const res = await api.sep10Token(address, signed)
    if (!res.ok || !res.token) throw new Error(res.error || 'Anchor rejected the signature')
    write(ANCHOR_KEY, address)
    setAnchorVerified(address)
    return { ...res, home_domain: challenge.home_domain }
  }

  // Company treasury → AI agent budget: built by the backend, signed in the wallet.
  async function fundAgent(amount, asset) {
    const built = await api.fundAgentBuild(address, amount, asset)
    const signed = await signWithWallet(built.xdr, {
      address,
      networkPassphrase: built.network_passphrase,
    })
    return api.fundAgentSubmit(address, signed)
  }

  return {
    address,
    anchorVerified: Boolean(address) && anchorVerified === address,
    setAddress,
    connect,
    disconnect,
    verifyAnchor,
    fundAgent,
  }
}
