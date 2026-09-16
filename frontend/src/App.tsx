import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { CaseProvider } from './context/CaseContext';
import Login from './pages/Login';
import CaseSelect from './pages/CaseSelect';
import Dashboard from './pages/Dashboard';
import Overview from './pages/Overview';
import GraphExplorer from './pages/GraphExplorer';
import Leads from './pages/Leads';
import ReviewQueue from './pages/ReviewQueue';
import WomenSafety from './pages/WomenSafety';
import SelfEvaluation from './pages/SelfEvaluation';
import AuditChain from './pages/AuditChain';
import type { ReactNode } from 'react';

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/cases" element={<RequireAuth><CaseSelect /></RequireAuth>} />
      <Route path="/dashboard/:caseId" element={<RequireAuth><Dashboard /></RequireAuth>}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<Overview />} />
        <Route path="graph" element={<GraphExplorer />} />
        <Route path="leads" element={<Leads />} />
        <Route path="review-queue" element={<ReviewQueue />} />
        <Route path="women-safety" element={<WomenSafety />} />
        <Route path="evaluation" element={<SelfEvaluation />} />
        <Route path="audit" element={<AuditChain />} />
      </Route>
      <Route path="*" element={<Navigate to="/cases" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <CaseProvider>
        <AppRoutes />
      </CaseProvider>
    </AuthProvider>
  );
}
