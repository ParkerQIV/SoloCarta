import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface Run {
  id: string
  feature_name: string
  status: string
  current_step: string | null
  gate_score: number | null
  gate_decision: string | null
  created_at: string
}

interface Stats {
  total_runs: number
  passed: number
  failed: number
  errored: number
  pass_rate: number
  avg_gate_score: number | null
  most_common_failure_agent: string | null
}

export default function Dashboard() {
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/runs').then((r) => {
        if (!r.ok) throw new Error(`API error: ${r.status}`)
        return r.json()
      }),
      fetch('/api/stats').then((r) => r.ok ? r.json() : null),
    ])
      .then(([runsData, statsData]) => {
        setRuns(runsData)
        setStats(statsData)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const statusColor = (status: string) => {
    switch (status) {
      case 'passed': return 'text-green-400'
      case 'failed': return 'text-red-400'
      case 'running': return 'text-yellow-400'
      case 'error': return 'text-red-500'
      default: return 'text-gray-400'
    }
  }

  if (loading) return <p className="text-gray-500">Loading...</p>

  if (error) return (
    <div className="rounded-lg border border-red-800 bg-red-950 p-4 text-sm text-red-300">
      Failed to load runs: {error}
    </div>
  )

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Pipeline Runs</h1>
      {stats && stats.total_runs > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold">{stats.total_runs}</p>
            <p className="text-xs text-gray-500">Total Runs</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold text-green-400">{stats.pass_rate}%</p>
            <p className="text-xs text-gray-500">Pass Rate</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold">{stats.avg_gate_score ?? '—'}</p>
            <p className="text-xs text-gray-500">Avg Gate Score</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">
              {stats.most_common_failure_agent ?? '—'}
            </p>
            <p className="text-xs text-gray-500">Top Failure Agent</p>
          </div>
        </div>
      )}
      {runs.length === 0 ? (
        <p className="text-gray-500">
          No runs yet.{' '}
          <Link to="/new" className="text-blue-400 hover:underline">
            Create one
          </Link>
        </p>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <Link
              key={run.id}
              to={`/run/${run.id}`}
              className="block rounded-lg border border-gray-800 p-4 hover:border-gray-700"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">{run.feature_name}</h2>
                  <p className="text-sm text-gray-500">
                    {run.current_step ?? 'pending'}
                  </p>
                </div>
                <span className={`text-sm font-medium ${statusColor(run.status)}`}>
                  {run.status}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
