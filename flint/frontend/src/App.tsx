import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './components/AppShell';
import TerminologyApp from './features/terminology/TerminologyApp';
import ClinicalApp from './features/clinical/ClinicalApp';
import AdminApp from './features/admin/AdminApp';
import MCPChatPage from './MCPChatPage';
import SystemApp from './features/system/SystemApp';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/admin" replace />} />
          <Route path="/terminology" element={<TerminologyApp />} />
          <Route path="/clinical" element={<ClinicalApp />} />
          <Route path="/admin" element={<AdminApp />} />
          <Route path="/mcp-chat" element={<MCPChatPage />} />
          <Route path="/system" element={<SystemApp />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
