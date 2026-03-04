import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function NewRun() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    repo_url: '',
    base_branch: 'main',
    feature_name: '',
    requirements: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })

      if (!res.ok) {
        const body = await res.json().catch(() => null)
        const detail = body?.detail
        const msg = Array.isArray(detail)
          ? detail.map((d: { msg: string }) => d.msg).join(', ')
          : detail || `Error ${res.status}`
        setError(msg)
        setSubmitting(false)
        return
      }

      const run = await res.json()
      await fetch(`/api/runs/${run.id}/start`, { method: 'POST' })
      navigate(`/run/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Network error')
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">New Pipeline Run</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-300">
            {error}
          </div>
        )}
        <div>
          <label className="mb-1 block text-sm text-gray-400">Repository URL</label>
          <input
            type="text"
            value={form.repo_url}
            onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            placeholder="https://github.com/user/repo or /path/to/local/repo"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Base Branch</label>
          <input
            type="text"
            value={form.base_branch}
            onChange={(e) => setForm({ ...form, base_branch: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Feature Name</label>
          <input
            type="text"
            value={form.feature_name}
            onChange={(e) => setForm({ ...form, feature_name: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            placeholder="add user authentication"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Requirements</label>
          <textarea
            value={form.requirements}
            onChange={(e) => setForm({ ...form, requirements: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            rows={6}
            placeholder="Describe what you want built..."
            required
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {submitting ? 'Starting...' : 'Start Pipeline'}
        </button>
      </form>
    </div>
  )
}
