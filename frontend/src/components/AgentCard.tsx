interface Props {
  name: string
  output: string | null
  status: 'pending' | 'running' | 'completed'
  onClick?: () => void
}

export default function AgentCard({ name, output, status, onClick }: Props) {
  const isClickable = onClick && output
  return (
    <div
      className={`rounded-lg border border-gray-800 p-4 ${
        isClickable ? 'cursor-pointer hover:border-gray-600' : ''
      }`}
      onClick={isClickable ? onClick : undefined}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold capitalize">{name} Agent</h3>
        <span className={`text-xs ${
          status === 'completed' ? 'text-green-400' :
          status === 'running' ? 'text-yellow-400' :
          'text-gray-500'
        }`}>
          {status}
        </span>
      </div>
      {output && (
        <pre className="max-h-64 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-300">
          {output}
        </pre>
      )}
    </div>
  )
}
