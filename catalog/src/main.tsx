import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './Layout'
import App from './App'
import CameraGrid from './pages/CameraGrid'
import './index.css'
import './i18n/config'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <BrowserRouter>
            <Routes>
                <Route element={<Layout />}>
                    <Route index element={<App />} />
                    <Route path="cameras" element={<CameraGrid />} />
                </Route>
            </Routes>
        </BrowserRouter>
    </React.StrictMode>,
)
