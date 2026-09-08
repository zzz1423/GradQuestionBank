import { useState, useEffect, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../api';
import type { Subject, Chapter } from '../types';

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const isActive = (prefix: string) =>
    location.pathname === prefix || location.pathname.startsWith(prefix + '/');

  const [toast, setToast] = useState<{ msg: string; color: string } | null>(null);
  const [showExport, setShowExport] = useState(false);
  const [exportSubjects, setExportSubjects] = useState<Subject[]>([]);
  const [exportSubjectId, setExportSubjectId] = useState('');
  const [exportChapters, setExportChapters] = useState<Chapter[]>([]);
  const [exportChapterId, setExportChapterId] = useState('');

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    api.subjects().then(d => setExportSubjects(d as Subject[])).catch(() => {});
  }, []);

  const handleExportSubjectChange = async (subjectId: string) => {
    setExportSubjectId(subjectId);
    setExportChapterId('');
    setExportChapters([]);
    if (!subjectId) return;
    try {
      const data = await api.subjectDetail(Number(subjectId)) as { chapters: Chapter[] };
      setExportChapters(data.chapters || []);
    } catch {
      setExportChapters([]);
    }
  };

  const openExport = () => {
    setShowExport(true);
    setExportSubjectId('');
    setExportChapterId('');
    setExportChapters([]);
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const result: Record<string, string> = await api.importFile(file) as Record<string, string>;
        setToast({ msg: result.message || '导入成功', color: 'success' });
      } catch (e: unknown) {
        setToast({ msg: (e as Error).message, color: 'danger' });
      }
    };
    input.click();
  };

  return (
    <div className="container-fluid">
      <div className="row">
        {/* Sidebar */}
        <nav className="col-md-2 sidebar py-3 d-none d-md-block">
          <h5 className="px-3 mb-3"><i className="bi bi-book"></i> 考研题库</h5>
          <ul className="nav flex-column">
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/' ? 'active' : ''}`} to="/">
                <i className="bi bi-house"></i> 概览
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${isActive('/exams') ? 'active' : ''}`} to="/exams">
                <i className="bi bi-mortarboard"></i> 考试管理
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${isActive('/subjects') ? 'active' : ''}`} to="/subjects">
                <i className="bi bi-collection"></i> 知识点管理
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/practice' ? 'active' : ''}`} to="/practice">
                <i className="bi bi-journal-check"></i> 做题记录
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${isActive('/questions') ? 'active' : ''}`} to="/questions">
                <i className="bi bi-journal-text"></i> 题目列表
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/statistics' ? 'active' : ''}`} to="/statistics">
                <i className="bi bi-bar-chart"></i> 统计分析
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/pdf-import' ? 'active' : ''}`} to="/pdf-import">
                <i className="bi bi-file-earmark-pdf"></i> PDF 导入
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/settings' ? 'active' : ''}`} to="/settings">
                <i className="bi bi-gear"></i> 设置
              </Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/dedup' ? 'active' : ''}`} to="/dedup">
                <i className="bi bi-search"></i> 知识点去重
              </Link>
            </li>
            <hr />
            <li className="nav-item">
              <a className="nav-link" href="#" onClick={(e) => { e.preventDefault(); openExport(); }}>
                <i className="bi bi-download"></i> 导出题库
              </a>
            </li>
            <li className="nav-item">
              <a className="nav-link" href="#" onClick={(e) => { e.preventDefault(); handleImport(); }}>
                <i className="bi bi-upload"></i> 导入题库
              </a>
            </li>
          </ul>
        </nav>

        {/* Main */}
        <main className="col-md-10 py-3 px-4">
          {/* Mobile nav */}
          <nav className="navbar navbar-expand-md d-md-none mb-3">
            <div className="container-fluid">
              <Link className="navbar-brand" to="/"><i className="bi bi-book"></i> 考研题库</Link>
              <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mobileNav">
                <span className="navbar-toggler-icon"></span>
              </button>
              <div className="collapse navbar-collapse" id="mobileNav">
                <ul className="navbar-nav">
                  <li><Link className="nav-link" to="/">概览</Link></li>
                  <li><Link className="nav-link" to="/subjects">知识点管理</Link></li>
                  <li><Link className="nav-link" to="/questions">题目列表</Link></li>
                  <li><Link className="nav-link" to="/statistics">统计分析</Link></li>
                  <li><Link className="nav-link" to="/pdf-import">PDF 导入</Link></li>
                  <li><Link className="nav-link" to="/settings">设置</Link></li>
                </ul>
              </div>
            </div>
          </nav>

          {toast && (
            <div className="position-fixed top-0 end-0 p-3" style={{ zIndex: 1050 }}>
              <div className={`toast show align-items-center text-bg-${toast.color} border-0`} role="alert">
                <div className="d-flex">
                  <div className="toast-body">{toast.msg}</div>
                  <button type="button" className="btn-close btn-close-white me-2 m-auto" onClick={() => setToast(null)}></button>
                </div>
              </div>
            </div>
          )}

          {showExport && (
            <div
              className="d-flex align-items-center justify-content-center"
              style={{ position: 'fixed', inset: 0, zIndex: 1055, backgroundColor: 'rgba(0,0,0,0.5)' }}
              onClick={() => setShowExport(false)}
            >
              <div className="card w-100" style={{ maxWidth: 480 }} onClick={e => e.stopPropagation()}>
                <div className="card-header d-flex justify-content-between align-items-center">
                  <span><i className="bi bi-download me-1"></i> 导出题库</span>
                  <button type="button" className="btn-close" aria-label="关闭" onClick={() => setShowExport(false)}></button>
                </div>
                <div className="card-body">
                  <div className="mb-3">
                    <label className="form-label">学科</label>
                    <select
                      className="form-select"
                      value={exportSubjectId}
                      onChange={e => handleExportSubjectChange(e.target.value)}
                    >
                      <option value="">全部学科</option>
                      {exportSubjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div className="mb-3">
                    <label className="form-label">章节</label>
                    <select
                      className="form-select"
                      value={exportChapterId}
                      disabled={!exportSubjectId}
                      onChange={e => setExportChapterId(e.target.value)}
                    >
                      <option value="">全部章节</option>
                      {exportChapters.map(ch => <option key={ch.id} value={ch.id}>{ch.name}</option>)}
                    </select>
                  </div>
                  <p className="text-muted small mb-0">
                    导出文件中的知识点只包含所选学科/章节内的条目。
                  </p>
                </div>
                <div className="card-footer d-flex justify-content-end gap-2">
                  <button className="btn btn-outline-secondary" onClick={() => setShowExport(false)}>取消</button>
                  <a
                    className="btn btn-primary"
                    href={api.exportDownload(
                      exportSubjectId ? Number(exportSubjectId) : undefined,
                      exportChapterId ? Number(exportChapterId) : undefined,
                    )}
                    onClick={() => setShowExport(false)}
                  >
                    <i className="bi bi-download me-1"></i> 导出
                  </a>
                </div>
              </div>
            </div>
          )}

          {children}
        </main>
      </div>
    </div>
  );
}
