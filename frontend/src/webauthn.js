function b64urlToBuffer(value) {
  const b64url = typeof value === 'string' ? value : bufferToB64url(value)
  const pad = '='.repeat((4 - (b64url.length % 4)) % 4)
  const b64 = (b64url.replace(/-/g, '+').replace(/_/g, '/') + pad)
  const raw = atob(b64)
  const buf = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i += 1) buf[i] = raw.charCodeAt(i)
  return buf.buffer
}

function bufferToB64url(buf) {
  const bytes = buf instanceof ArrayBuffer ? new Uint8Array(buf) : new Uint8Array(buf.buffer || buf)
  let str = ''
  bytes.forEach((b) => {
    str += String.fromCharCode(b)
  })
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function parseOptions(payload) {
  if (typeof payload === 'string') return JSON.parse(payload)
  if (payload?.options) {
    return typeof payload.options === 'string' ? JSON.parse(payload.options) : payload.options
  }
  return payload
}

function publicKeyFromCreateOptions(raw) {
  const opts = parseOptions(raw)
  return {
    ...opts,
    challenge: b64urlToBuffer(opts.challenge),
    user: {
      ...opts.user,
      id: b64urlToBuffer(opts.user.id),
    },
    excludeCredentials: (opts.excludeCredentials || []).map((c) => ({
      ...c,
      id: b64urlToBuffer(c.id),
    })),
  }
}

function publicKeyFromRequestOptions(raw) {
  const opts = parseOptions(raw)
  return {
    ...opts,
    challenge: b64urlToBuffer(opts.challenge),
    allowCredentials: (opts.allowCredentials || []).map((c) => ({
      ...c,
      id: b64urlToBuffer(c.id),
    })),
  }
}

function credentialToJSON(cred) {
  const response = cred.response
  const json = {
    id: cred.id,
    rawId: bufferToB64url(cred.rawId),
    type: cred.type,
    authenticatorAttachment: cred.authenticatorAttachment || 'platform',
    clientExtensionResults: cred.getClientExtensionResults?.() || {},
    response: {
      clientDataJSON: bufferToB64url(response.clientDataJSON),
    },
  }
  if (response.attestationObject) {
    json.response.attestationObject = bufferToB64url(response.attestationObject)
  }
  if (response.authenticatorData) {
    json.response.authenticatorData = bufferToB64url(response.authenticatorData)
  }
  if (response.signature) {
    json.response.signature = bufferToB64url(response.signature)
  }
  if (response.userHandle) {
    json.response.userHandle = bufferToB64url(response.userHandle)
  }
  return json
}

export async function createPasskey(optionsPayload) {
  const publicKey = publicKeyFromCreateOptions(optionsPayload)
  const cred = await navigator.credentials.create({ publicKey })
  if (!cred) throw new Error('Passkey creation cancelled')
  return credentialToJSON(cred)
}

export async function getPasskey(optionsPayload) {
  const publicKey = publicKeyFromRequestOptions(optionsPayload)
  const cred = await navigator.credentials.get({ publicKey })
  if (!cred) throw new Error('Passkey login cancelled')
  return credentialToJSON(cred)
}

export function passkeysSupported() {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential
}
