interface Props {
  name: string
  output: string | null
  status: 'pending' | 'running' | 'completed' | 'error'
  error?: string | null
}

export default function AgentCard({ name, output, status, error }: Props) {
  return (
    <div className="rounded-lg border border-gray-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold capitalize">{name} Agent</h3>
        <span className={`text-xs ${
          status === 'completed' ? 'text-green-400' :
          status === 'running' ? 'text-yellow-400' :
          status === 'error' ? 'text-red-400' :
          'text-gray-500'
        }`}>
          {status}
        </span>
      </div>
      {error && (
        <div className="mt-2 rounded bg-red-950 p-2 text-xs text-red-300">
          {error}
        </div>
      )}
      {output && (
        <pre className="max-h-64 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-300">
          {output}
        </pre>
      )}
    </div>
  )
}
