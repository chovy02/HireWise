import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { ToastProvider } from './context/ToastContext.jsx'
import { ProjectProvider } from './context/ProjectContext.jsx'
import { PageContextProvider } from './context/PageContext.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <ProjectProvider>
            {/* Bọc TRONG ProjectProvider và NGOÀI App: các trang bên trong App công bố
                vị trí đang mở, còn CopilotChat (trong Layout) đọc ra để gửi kèm chat. */}
            <PageContextProvider>
              <App />
            </PageContextProvider>
          </ProjectProvider>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)
