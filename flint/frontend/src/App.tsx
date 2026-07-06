import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginGate from './components/LoginGate';
import AppShell from './components/AppShell';
import HomePage from './features/home/HomePage';
import TerminologyApp from './features/terminology/TerminologyApp';
import ClinicalApp from './features/clinical/ClinicalApp';
import AdminApp from './features/admin/AdminApp';
import MCPChatPage from './MCPChatPage';
import SystemApp from './features/system/SystemApp';
import AuthCallback from './features/auth/AuthCallback';
import PatientPortalPage from './features/patient/PatientPortalPage';

function HomeRedirect() {
  const { roles } = useAuth();
  if (roles.includes('fhir-patient')) return <Navigate to="/my-health" replace />;
  return <HomePage />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/callback" element={<AuthCallback />} />
          <Route element={<LoginGate />}>
            <Route element={<AppShell />}>
              <Route index element={<HomeRedirect />} />
              <Route path="/terminology" element={<TerminologyApp />} />
              <Route path="/clinical" element={<ClinicalApp />} />
              <Route path="/admin" element={<AdminApp />} />
              <Route path="/mcp-chat" element={<MCPChatPage />} />
              <Route path="/system" element={<SystemApp />} />
              <Route path="/my-health" element={<PatientPortalPage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
