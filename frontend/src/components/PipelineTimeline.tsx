const STEPS = ['sandbox_setup', 'pm', 'architect', 'planner', 'dev', 'qa', 'reviewer', 'gatekeeper']

interface Props {
  currentStep: string | null
  status: string
}

export default function PipelineTimeline({ currentStep, status }: Props) {
  const currentIndex = currentStep ? STEPS.indexOf(currentStep) : -1

  return (
    <div className="flex gap-2">
      {STEPS.map((step, i) => {
        let color = 'bg-gray-800 text-gray-500'
        if (status === 'passed' || status === 'failed') {
          color = i <= currentIndex ? 'bg-gray-700 text-gray-300' : 'bg-gray-800 text-gray-500'
        } else if (i < currentIndex) {
          color = 'bg-green-900 text-green-300'
        } else if (i === currentIndex) {
          color = 'bg-yellow-900 text-yellow-300'
        }

        return (
          <div key={step} className={`rounded px-3 py-1 text-xs font-medium ${color}`}>
            {step}
          </div>
        )
      })}
    </div>
  )
}
