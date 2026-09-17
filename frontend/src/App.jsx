import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import Rules from './pages/Rules'
import Console from './pages/Console'
import Balance from './pages/Balance'
import Supplier from './pages/Supplier'
import { LanguageProvider } from './hooks/useLanguage.jsx'
import { Toast } from './components/Toast'

export default function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Onboarding />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="/console" element={<Console />} />
            <Route path="/balance" element={<Balance />} />
            <Route path="/supplier" element={<Supplier />} />
          </Routes>
        </Layout>
        <Toast />
      </BrowserRouter>
    </LanguageProvider>
  )
}
