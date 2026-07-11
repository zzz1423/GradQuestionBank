import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import type { Chapter, KnowledgePoint } from '../types';

interface TreeKP extends KnowledgePoint {
  children?: TreeKP[];
}

export default function ChapterDetail() {
  const { id } = useParams();
  const chapterId = Number(id);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [kps, setKps] = useState<TreeKP[]>([]);
  const [kpName, setKpName] = useState('');
  const [kpDesc, setKpDesc] = useState('');
  const [showModal, setShowModal] = useState(false);

  const load = () => {
    api.chapterDetail(chapterId).then(d => {
      const data = d as { chapter: Chapter; knowledge_points: KnowledgePoint[] };
      setChapter(data.chapter);
      setKps(data.knowledge_points);
    });
  };
  useEffect(() => { load(); }, [chapterId]);

  const addKP = async () => {
    if (!kpName.trim()) return;
    try {
      await api.addKP(chapterId, kpName.trim(), kpDesc.trim() || undefined);
      setKpName('');
      setKpDesc('');
      setShowModal(false);
      load();
    } catch (e) { alert((e as Error).message); }
  };

  const deleteKP = async (kpId: number) => {
    if (!confirm('确定删除此知识点？')) return;
    try {
      await api.deleteKP(kpId);
      load();
    } catch (e) { alert((e as Error).message); }
  };

  const renderKPList = (items: TreeKP[], depth = 0) => {
    return items.map(kp => (
      <React.Fragment key={kp.id}>
        <tr>
          <td style={{ paddingLeft: `${16 + depth * 24}px` }}>
            {depth > 0 && <span className="text-muted me-1">{'└─'}</span>}
            <strong>{kp.name}</strong>
            {kp.description && <><br /><small className="text-muted">{kp.description}</small></>}
          </td>
          <td><span className="badge bg-info">{kp.question_count || 0}</span></td>
          <td>
            <button className="btn btn-sm btn-outline-danger" onClick={() => deleteKP(kp.id)} title="删除">
              <i className="bi bi-trash"></i>
            </button>
          </td>
        </tr>
        {kp.children && kp.children.length > 0 && renderKPList(kp.children, depth + 1)}
      </React.Fragment>
    ));
  };

  if (!chapter) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to="/subjects">学科管理</Link></li>
          <li className="breadcrumb-item"><Link to={`/subjects/${chapter.subject_id}`}>{chapter.subject_name}</Link></li>
          <li className="breadcrumb-item active">{chapter.name}</li>
        </ol>
      </nav>

      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4>{chapter.name}</h4>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          <i className="bi bi-plus"></i> 添加知识点
        </button>
      </div>

      <div className="card">
        <div className="card-body p-0">
          <table className="table table-hover mb-0">
            <thead className="table-light">
              <tr><th>知识点</th><th>关联题目数</th><th style={{ width: 80 }}>操作</th></tr>
            </thead>
            <tbody>
              {kps.map(kp => (
                <tr key={kp.id}>
                  <td>
                    <strong>{kp.name}</strong>
                    {kp.description && <><br /><small className="text-muted">{kp.description}</small></>}
                  </td>
                  <td><span className="badge bg-info">{kp.question_count}</span></td>
                  <td>
                    <button className="btn btn-sm btn-outline-danger" onClick={() => deleteKP(kp.id)}>
                      <i className="bi bi-trash"></i>
                    </button>
                  </td>
                </tr>
              ))}
              {kps.length === 0 && <tr><td colSpan={3} className="text-center text-muted">暂无知识点</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowModal(false)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">添加知识点</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">知识点名称</label>
                  <input type="text" className="form-control" value={kpName} onChange={e => setKpName(e.target.value)} required />
                </div>
                <div className="mb-3">
                  <label className="form-label">描述（可选）</label>
                  <textarea className="form-control" rows={2} value={kpDesc} onChange={e => setKpDesc(e.target.value)} />
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
                <button className="btn btn-primary" onClick={addKP}>添加</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
