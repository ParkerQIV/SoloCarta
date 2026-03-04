import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewRun from './pages/NewRun'
import RunDetail from './pages/RunDetail'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="border-b border-gray-800 px-6 py-4">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-xl font-bold text-white">
              SoloCarta
            </Link>
            <Link to="/new" className="text-sm text-gray-400 hover:text-white">
              New Run
            </Link>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/new" element={<NewRun />} />
            <Route path="/run/:id" element={<RunDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
