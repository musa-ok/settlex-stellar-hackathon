// Stellar Wallets Kit: one modal for Freighter, xBull, Albedo, Lobstr, Hana, Rabet…
// The kit keeps the chosen wallet in localStorage, so signing works after a reload.
import { StellarWalletsKit } from '@creit.tech/stellar-wallets-kit/sdk'
import { defaultModules } from '@creit.tech/stellar-wallets-kit/modules/utils'
import { Networks } from '@creit.tech/stellar-wallets-kit/types'

let initialized = false

function kit() {
  if (!initialized) {
    StellarWalletsKit.init({ modules: defaultModules(), network: Networks.TESTNET })
    initialized = true
  }
  return StellarWalletsKit
}

function hasSelectedWallet() {
  try {
    return Boolean(kit().selectedModule)
  } catch {
    return false
  }
}

export async function connectWallet() {
  const { address } = await kit().authModal()
  return address
}

export async function signWithWallet(xdr, { address, networkPassphrase }) {
  if (!hasSelectedWallet()) await connectWallet()
  const { signedTxXdr } = await kit().signTransaction(xdr, { address, networkPassphrase })
  return signedTxXdr
}

export async function disconnectWallet() {
  try {
    await kit().disconnect()
  } catch {
    /* already disconnected */
  }
}

// Kit errors are plain objects ({ code, message }), backend errors are JSON text.
export function walletErrorText(err) {
  if (!err) return ''
  if (typeof err === 'string') return err
  try {
    const { detail } = JSON.parse(err.message)
    return [detail.error, detail.message].filter(Boolean).join(' — ')
  } catch {
    return err.message || String(err)
  }
}
