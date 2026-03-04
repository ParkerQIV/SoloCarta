import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useSSE } from '../hooks/useSSE'
import PipelineTimeline from '../components/PipelineTimeline'

interface Run {
  id: string
  feature_name: string
  requirements: string
  status: string
  current_step: string | null
  gate_score: number | null
  gate_decision: string | null
  error: string | null
  pr_url: string | null
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const { events } = useSSE(`/api/stream/${id}`)

  useEffect(() => {
    fetch(`/api/runs/${id}`)
      .then((r) => r.json())
      .then(setRun)
  }, [id])

  // Refresh run data when SSE events arrive
  useEffect(() => {
    if (events.length > 0) {
      fetch(`/api/runs/${id}`)
        .then((r) => r.json())
        .then(setRun)
    }
  }, [events.length, id])

  if (!run) return <p className="text-gray-500">Loading...</p>

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">{run.feature_name}</h1>
      <p className="mb-6 text-sm text-gray-500">{run.requirements}</p>

      <PipelineTimeline currentStep={run.current_step} status={run.status} />

      <div className="mt-6 rounded-lg border border-gray-800 p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Status:</span>{' '}
            <span className="font-medium">{run.status}</span>
          </div>
          <div>
            <span className="text-gray-500">Current Step:</span>{' '}
            <span className="font-medium">{run.current_step ?? '\u2014'}</span>
          </div>
          {run.gate_score !== null && (
            <div>
              <span className="text-gray-500">Gate Score:</span>{' '}
              <span className="font-medium">{run.gate_score}/15</span>
            </div>
          )}
          {run.gate_decision && (
            <div>
              <span className="text-gray-500">Decision:</span>{' '}
              <span className={`font-medium ${
                run.gate_decision === 'PASS' ? 'text-green-400' : 'text-red-400'
              }`}>
                {run.gate_decision}
              </span>
            </div>
          )}
          {run.pr_url && (
            <div className="col-span-2">
              <a href={run.pr_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
                View Pull Request
              </a>
            </div>
          )}
          {run.error && (
            <div className="col-span-2">
              <pre className="rounded bg-red-950 p-3 text-xs text-red-300">{run.error}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
