import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useSSE } from '../hooks/useSSE'
import PipelineTimeline from '../components/PipelineTimeline'
import AgentCard from '../components/AgentCard'
import DiffViewer from '../components/DiffViewer'
import LogViewer from '../components/LogViewer'

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

interface AgentOutputData {
  id: string
  run_id: string
  agent_name: string
  output_text: string
  status: string
  started_at: string | null
  completed_at: string | null
}

const AGENT_NAMES = ['pm', 'architect', 'planner', 'dev', 'qa', 'reviewer', 'gatekeeper'] as const
const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const [outputs, setOutputs] = useState<AgentOutputData[]>([])
  const [activeAgent, setActiveAgent] = useState<string | null>(null)
  const [diff, setDiff] = useState<string | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const { events } = useSSE(`/api/stream/${id}`)

  const fetchOutputs = useCallback(() => {
    fetch(`/api/runs/${id}/outputs`)
      .then((r) => r.json())
      .then(setOutputs)
  }, [id])

  const fetchDiff = useCallback(() => {
    setDiffLoading(true)
    fetch(`/api/runs/${id}/diff`)
      .then((r) => {
        if (!r.ok) return null
        return r.json()
      })
      .then((data) => {
        if (data?.has_changes) setDiff(data.diff)
      })
      .finally(() => setDiffLoading(false))
  }, [id])

  useEffect(() => {
    fetch(`/api/runs/${id}`)
      .then((r) => r.json())
      .then((data: Run) => {
        setRun(data)
        if (TERMINAL_STATUSES.includes(data.status)) {
          fetchDiff()
        }
      })
    fetchOutputs()
  }, [id, fetchOutputs, fetchDiff])

  // Handle SSE events
  useEffect(() => {
    if (events.length === 0) return
    const latest = events[events.length - 1]

    if (latest.event === 'status' || latest.event === 'pipeline_complete') {
      fetch(`/api/runs/${id}`)
        .then((r) => r.json())
        .then(setRun)
    }

    if (latest.event === 'agent_start') {
      const data = latest.data as { agent: string }
      setActiveAgent(data.agent)
    }

    if (latest.event === 'agent_complete') {
      const data = latest.data as { agent: string }
      setActiveAgent(null)
      fetchOutputs()
      if (data.agent === 'dev') {
        fetchDiff()
      }
    }

    if (latest.event === 'pipeline_complete') {
      setActiveAgent(null)
      fetchOutputs()
      fetchDiff()
    }
  }, [events.length, id, fetchOutputs, fetchDiff])

  if (!run) return <p className="text-gray-500">Loading...</p>

  const outputsByAgent = new Map(outputs.map((o) => [o.agent_name, o]))
  const selectedOutput = selectedAgent ? outputsByAgent.get(selectedAgent) : null

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">{run.feature_name}</h1>
      <p className="mb-6 text-sm text-gray-500">{run.requirements}</p>

      <PipelineTimeline currentStep={run.current_step} status={run.status} />

      <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {AGENT_NAMES.map((agent) => {
          const agentOutput = outputsByAgent.get(agent)
          let status: 'pending' | 'running' | 'completed' = 'pending'
          if (agentOutput) {
            status = 'completed'
          } else if (activeAgent === agent) {
            status = 'running'
          }
          return (
            <AgentCard
              key={agent}
              name={agent}
              output={agentOutput?.output_text ?? null}
              status={status}
              onClick={() => setSelectedAgent(agent)}
            />
          )
        })}
      </div>

      {diffLoading && (
        <p className="mt-6 text-sm text-gray-500">Loading diff...</p>
      )}

      {diff && !diffLoading && (
        <div className="mt-6">
          <DiffViewer diff={diff} />
        </div>
      )}

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

      {selectedAgent && selectedOutput && (
        <LogViewer
          agentName={selectedAgent}
          output={selectedOutput.output_text}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  )
}
