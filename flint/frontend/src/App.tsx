import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import LoginGate from './components/LoginGate';
import AppShell from './components/AppShell';
import HomePage from './features/home/HomePage';
import TerminologyApp from './features/terminology/TerminologyApp';
import ClinicalApp from './features/clinical/ClinicalApp';
import AdminApp from './features/admin/AdminApp';
import MCPChatPage from './MCPChatPage';
import SystemApp from './features/system/SystemApp';
import AuthCallback from './features/auth/AuthCallback';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/callback" element={<AuthCallback />} />
          <Route element={<LoginGate />}>
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="/terminology" element={<TerminologyApp />} />
              <Route path="/clinical" element={<ClinicalApp />} />
              <Route path="/admin" element={<AdminApp />} />
              <Route path="/mcp-chat" element={<MCPChatPage />} />
              <Route path="/system" element={<SystemApp />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
