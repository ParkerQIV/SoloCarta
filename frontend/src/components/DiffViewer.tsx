interface Props {
  diff: string
}

function classForLine(line: string): string {
  if (line.startsWith('diff ')) return 'font-bold text-gray-100'
  if (line.startsWith('+++') || line.startsWith('---')) return 'font-bold text-gray-400'
  if (line.startsWith('@@')) return 'text-blue-400'
  if (line.startsWith('+')) return 'text-green-400 bg-green-950/40'
  if (line.startsWith('-')) return 'text-red-400 bg-red-950/40'
  return 'text-gray-300'
}

export default function DiffViewer({ diff }: Props) {
  const lines = diff.split('\n')

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 overflow-hidden">
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2">
        <h3 className="text-sm font-semibold text-gray-200">Code Changes</h3>
      </div>
      <pre className="max-h-[600px] overflow-auto p-4 text-xs leading-5">
        {lines.map((line, i) => (
          <div key={i} className={classForLine(line)}>
            {line || '\n'}
          </div>
        ))}
      </pre>
    </div>
  )
}
