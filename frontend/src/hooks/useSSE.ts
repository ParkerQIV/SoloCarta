import { useEffect, useRef, useState } from 'react'

interface SSEEvent {
  event: string
  data: unknown
}

export function useSSE(url: string) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const source = new EventSource(url)
    sourceRef.current = source

    source.onopen = () => setConnected(true)

    source.onmessage = (e) => {
      try {
        const data: unknown = JSON.parse(e.data as string)
        setEvents((prev) => [...prev, { event: 'message', data }])
      } catch {
        // ignore parse errors
      }
    }

    source.addEventListener('status', (e) => {
      const data: unknown = JSON.parse((e as MessageEvent).data as string)
      setEvents((prev) => [...prev, { event: 'status', data }])
    })

    source.addEventListener('agent_start', (e) => {
      const data: unknown = JSON.parse((e as MessageEvent).data as string)
      setEvents((prev) => [...prev, { event: 'agent_start', data }])
    })

    source.addEventListener('agent_complete', (e) => {
      const data: unknown = JSON.parse((e as MessageEvent).data as string)
      setEvents((prev) => [...prev, { event: 'agent_complete', data }])
    })

    source.addEventListener('pipeline_complete', (e) => {
      const data: unknown = JSON.parse((e as MessageEvent).data as string)
      setEvents((prev) => [...prev, { event: 'pipeline_complete', data }])
      source.close()
    })

    source.onerror = () => {
      setConnected(false)
      source.close()
    }

    return () => source.close()
  }, [url])

  return { events, connected }
}
