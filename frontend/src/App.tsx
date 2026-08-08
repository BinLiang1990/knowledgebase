import { Navigate, Route, Routes } from 'react-router-dom';
import { KnowledgeBaseListPage } from './pages/KnowledgeBaseListPage';
import { KnowledgePointListPage } from './pages/KnowledgePointListPage';
import { KnowledgePointDetailPage } from './pages/KnowledgePointDetailPage';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/knowledge-bases" replace />} />
      <Route path="/knowledge-bases" element={<KnowledgeBaseListPage />} />
      <Route path="/knowledge-bases/:kbId/knowledge-points" element={<KnowledgePointListPage />} />
      <Route path="/knowledge-bases/:kbId/knowledge-points/:kpId" element={<KnowledgePointDetailPage />} />
    </Routes>
  );
}
