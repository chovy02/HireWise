import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Login from './pages/Login.jsx'
import SignUp from './pages/SignUp.jsx'
import VerifyEmail from './pages/VerifyEmail.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Shortlisting from './pages/Shortlisting.jsx'
import CVAnalysis from './pages/CVAnalysis.jsx'
import AdminGateway from './pages/AdminGateway.jsx'

export default function App() {
  return (
    <Routes>
      {/* ---- Public auth routes ---- */}
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/verify" element={<VerifyEmail />} />

      {/* ---- Main app (sidebar shell). Public: the dashboard is the landing
           page; sign in / sign up live in the sidebar's bottom-left corner. ---- */}
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/shortlisting" element={<Shortlisting />} />
        <Route path="/cv-analysis" element={<CVAnalysis />} />
        <Route path="/admin" element={<AdminGateway />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
