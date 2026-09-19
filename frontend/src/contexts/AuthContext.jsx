import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { createPasskey, getPasskey, passkeysSupported } from '../webauthn'

const AuthContext = createContext(null)

const TOKEN_KEY = 'settlex_passkey_session'
const USER_KEY = 'settlex_passkey_user'

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [username, setUsername] = useState(() => localStorage.getItem(USER_KEY) || 'settlex-cfo')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const authenticated = Boolean(token)

  useEffect(() => {
    if (!token) return
    api.passkeyMe(token)
      .then((me) => {
        if (!me?.authenticated) {
          localStorage.removeItem(TOKEN_KEY)
          setToken('')
        } else if (me.username) {
          setUsername(me.username)
          localStorage.setItem(USER_KEY, me.username)
        }
      })
      .catch(() => {})
  }, [token])

  function persist(session) {
    localStorage.setItem(TOKEN_KEY, session.token)
    localStorage.setItem(USER_KEY, session.username)
    setToken(session.token)
    setUsername(session.username)
  }

  async function register(name = username) {
    setBusy(true)
    setError('')
    try {
      const opts = await api.passkeyRegisterOptions(name)
      const credential = await createPasskey(opts.options || opts)
      const session = await api.passkeyRegisterVerify(name, credential)
      persist(session)
      return session
    } catch (err) {
      setError(err.message || 'Passkey registration failed')
      throw err
    } finally {
      setBusy(false)
    }
  }

  async function login(name = username) {
    setBusy(true)
    setError('')
    try {
      const opts = await api.passkeyLoginOptions(name)
      const credential = await getPasskey(opts.options || opts)
      const session = await api.passkeyLoginVerify(name, credential)
      persist(session)
      return session
    } catch (err) {
      setError(err.message || 'Passkey login failed')
      throw err
    } finally {
      setBusy(false)
    }
  }

  // Signing step-up: prompts FaceID / TouchID again and returns a one-shot token
  // for a single approval. It is not persisted, so the login session is unchanged.
  async function confirmWithPasskey(name = username) {
    const opts = await api.passkeyLoginOptions(name)
    const credential = await getPasskey(opts.options || opts)
    const session = await api.passkeyLoginVerify(name, credential)
    return session.token
  }

  async function logout() {
    try {
      await api.passkeyLogout(token)
    } catch {
      /* ignore */
    }
    localStorage.removeItem(TOKEN_KEY)
    setToken('')
  }

  const value = useMemo(
    () => ({
      token,
      username,
      setUsername,
      authenticated,
      busy,
      error,
      supported: passkeysSupported(),
      register,
      login,
      logout,
      confirmWithPasskey,
    }),
    [token, username, authenticated, busy, error],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
