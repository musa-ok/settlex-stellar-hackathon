import { useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api'

export function useAgentConsole() {
  const [logs, setLogs] = useState([])
  const [turns, setTurns] = useState([])
  const [deal, setDeal] = useState(null)
  const [settlement, setSettlement] = useState(null)
  const [anchorSteps, setAnchorSteps] = useState([])
  const [negotiation, setNegotiation] = useState(null)
  const [connected, setConnected] = useState(false)
  const seen = useRef(new Set())

  function resetSession() {
    setTurns([])
    setDeal(null)
    setSettlement(null)
    setAnchorSteps([])
    setNegotiation(null)
  }

  useEffect(() => {
    let alive = true
    let ws
    let retry

    api.logs()
      .then((data) => {
        if (!alive) return
        data.forEach((l) => seen.current.add(l.id))
        setLogs(data)
      })
      .catch(() => {})

    api.listNegotiations()
      .then((list) => {
        if (!alive || !Array.isArray(list)) return
        const frozen = list.find(
          (n) => n.status === 'pending_multisig' || n.status === 'awaiting_approval',
        )
        if (frozen) setNegotiation(frozen)
      })
      .catch(() => {})

    const connect = () => {
      ws = new WebSocket(wsUrl())
      ws.onopen = () => alive && setConnected(true)
      ws.onclose = () => {
        if (!alive) return
        setConnected(false)
        retry = setTimeout(connect, 1500)
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.speaker && msg.message != null) {
            setTurns((prev) => [...prev, msg])
            if (msg.status === 'deal') setDeal(msg)
          }
          if (msg.type === 'anchor_step' && msg.message) {
            setAnchorSteps((prev) => [
              ...prev,
              { message: msg.message, level: msg.level || 'info' },
            ])
          }
          if (msg.type === 'log' && msg.data) {
            if (seen.current.has(msg.data.id)) return
            seen.current.add(msg.data.id)
            setLogs((prev) => [...prev, msg.data].slice(-300))
          }
          if (msg.type === 'settlement') {
            setSettlement(msg)
          }
          if (msg.type === 'negotiation' && msg.data) {
            setNegotiation(msg.data)
          }
        } catch {
          /* ignore */
        }
      }
    }
    connect()

    return () => {
      alive = false
      clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return { logs, turns, deal, settlement, anchorSteps, negotiation, setNegotiation, connected, resetSession }
}
