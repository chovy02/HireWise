import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'

// App shell: fixed sidebar on the left, scrollable content on the right.
// Each page renders its own top bar (most use <Topbar/>, CV Analysis is custom).
export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </div>
    </div>
  )
}
