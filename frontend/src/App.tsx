import { Navigate, Route, Routes } from 'react-router-dom';
import { KnowledgeBaseListPage } from './pages/KnowledgeBaseListPage';
import { KnowledgePointListPage } from './pages/KnowledgePointListPage';
import { KnowledgePointDetailPage } from './pages/KnowledgePointDetailPage';
import { DimensionsPage } from './pages/DimensionsPage';
import { KnowledgeBaseSettingsPage } from './pages/KnowledgeBaseSettingsPage';
import { OperationLogPage } from './pages/OperationLogPage';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/knowledge-bases" replace />} />
      <Route path="/knowledge-bases" element={<KnowledgeBaseListPage />} />
      <Route path="/dimensions" element={<DimensionsPage />} />
      <Route path="/change-log" element={<OperationLogPage />} />
      <Route path="/knowledge-bases/:kbId/knowledge-points" element={<KnowledgePointListPage />} />
      <Route path="/knowledge-bases/:kbId/knowledge-points/:kpId" element={<KnowledgePointDetailPage />} />
      <Route path="/knowledge-bases/:kbId/settings" element={<KnowledgeBaseSettingsPage />} />
    </Routes>
  );
}
