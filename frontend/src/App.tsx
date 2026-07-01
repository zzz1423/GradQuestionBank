import { BrowserRouter, Routes, Route } from 'react-router-dom';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.min.css';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Subjects from './pages/Subjects';
import SubjectDetail from './pages/SubjectDetail';
import ChapterDetail from './pages/ChapterDetail';
import Questions from './pages/Questions';
import QuestionDetail from './pages/QuestionDetail';
import AddQuestion from './pages/AddQuestion';
import EditQuestion from './pages/EditQuestion';
import ReviewKnowledge from './pages/ReviewKnowledge';
import BatchImport from './pages/BatchImport';
import Statistics from './pages/Statistics';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/subjects" element={<Subjects />} />
          <Route path="/subjects/:id" element={<SubjectDetail />} />
          <Route path="/chapters/:id" element={<ChapterDetail />} />
          <Route path="/questions" element={<Questions />} />
          <Route path="/questions/add" element={<AddQuestion />} />
          <Route path="/questions/batch" element={<BatchImport />} />
          <Route path="/questions/:id" element={<QuestionDetail />} />
          <Route path="/questions/:id/edit" element={<EditQuestion />} />
          <Route path="/questions/:id/review" element={<ReviewKnowledge />} />
          <Route path="/statistics" element={<Statistics />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
