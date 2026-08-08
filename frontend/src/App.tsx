import { Navigate, Route, Routes } from 'react-router-dom';
import { KnowledgeBaseListPage } from './pages/KnowledgeBaseListPage';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/knowledge-bases" replace />} />
      <Route path="/knowledge-bases" element={<KnowledgeBaseListPage />} />
    </Routes>
  );
}
