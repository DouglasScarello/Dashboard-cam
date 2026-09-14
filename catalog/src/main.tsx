import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './Layout'
import App from './App'
import CameraGrid from './pages/CameraGrid'
import CameraMap from './pages/CameraMap'
import Painel from './pages/Painel'
import Pessoas from './pages/Pessoas'
import Veiculos from './pages/Veiculos'
import AoVivo from './pages/AoVivo'
import Tatico from './pages/Tatico'
import Controle from './pages/Controle'
import CamerasTeste from './pages/CamerasTeste'
import './index.css'
import './i18n/config'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <BrowserRouter>
            <Routes>
                <Route element={<Layout />}>
                    <Route index element={<App />} />
                    <Route path="cameras" element={<CameraGrid />} />
                    <Route path="map" element={<CameraMap />} />
                    <Route path="painel" element={<Painel />} />
                    <Route path="pessoas" element={<Pessoas />} />
                    <Route path="veiculos" element={<Veiculos />} />
                    <Route path="ao-vivo" element={<AoVivo />} />
                    <Route path="tatico" element={<Tatico />} />
                    <Route path="controle" element={<Controle />} />
                    <Route path="cameras-teste" element={<CamerasTeste />} />
                </Route>
            </Routes>
        </BrowserRouter>
    </React.StrictMode>,
)
