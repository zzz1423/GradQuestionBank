import { useState, useEffect, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../api';

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const isActive = (prefix: string) =>
    location.pathname === prefix || location.pathname.startsWith(prefix + '/');

  const [toast, setToast] = useState<{ msg: string; color: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

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
              <Link className={`nav-link ${isActive('/subjects') ? 'active' : ''}`} to="/subjects">
                <i className="bi bi-collection"></i> 学科管理
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
              <Link className={`nav-link ${location.pathname === '/settings' ? 'active' : ''}`} to="/settings">
                <i className="bi bi-gear"></i> 设置
              </Link>
            </li>
            <hr />
            <li className="nav-item">
              <a className="nav-link" href={api.exportUrl}>
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
                  <li><Link className="nav-link" to="/subjects">学科管理</Link></li>
                  <li><Link className="nav-link" to="/questions">题目列表</Link></li>
                  <li><Link className="nav-link" to="/statistics">统计分析</Link></li>
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

          {children}
        </main>
      </div>
    </div>
  );
}
