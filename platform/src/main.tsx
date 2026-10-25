import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles/global.css'
import App from './app/App'
import { loadSettings } from './app/settings'
import { setThemeMode } from './app/theme'

// Before the first render, so the page never flashes the wrong theme.
setThemeMode(loadSettings().theme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
