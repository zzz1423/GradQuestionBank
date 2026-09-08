import React, { useEffect, useState, useCallback } from 'react';
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
  const [kps, setKps] = useState<KnowledgePoint[]>([]);
  const [kpName, setKpName] = useState('');
  const [kpDesc, setKpDesc] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [toast, setToast] = useState('');
  const [dragOverId, setDragOverId] = useState<number | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  }, []);

  const load = useCallback(() => {
    api.chapterDetail(chapterId).then(d => {
      const data = d as { chapter: Chapter; knowledge_points: KnowledgePoint[] };
      setChapter(data.chapter);
      setKps(data.knowledge_points);
    });
  }, [chapterId]);

  useEffect(() => { load(); }, [load]);

  // Build tree structure from flat KP list
  const buildTree = useCallback((flat: KnowledgePoint[]): TreeKP[] => {
    const byId = new Map<number, TreeKP>();
    flat.forEach(kp => byId.set(kp.id, { ...kp, children: [] }));
    const roots: TreeKP[] = [];
    flat.forEach(kp => {
      const node = byId.get(kp.id)!;
      const parentId = (kp as any).parent_id as number | null;
      if (parentId && byId.has(parentId)) {
        byId.get(parentId)!.children!.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  }, []);

  const tree = buildTree(kps);

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

  const moveKP = async (kpId: number, newParentId: number | null) => {
    try {
      await api.moveKP(kpId, newParentId);
      showToast('已移动知识点');
      load();
    } catch (e) {
      showToast('移动失败: ' + (e as Error).message);
    }
  };

  // Drag handlers
  const handleDragStart = (e: React.DragEvent, kpId: number) => {
    e.dataTransfer.setData('text/plain', String(kpId));
    e.dataTransfer.effectAllowed = 'move';
    setDraggingId(kpId);
  };

  const handleDragOver = (e: React.DragEvent, kpId: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverId(kpId);
  };

  const handleDragLeave = () => {
    setDragOverId(null);
  };

  const handleDrop = (e: React.DragEvent, targetId: number) => {
    e.preventDefault();
    setDragOverId(null);
    setDraggingId(null);
    const sourceId = Number(e.dataTransfer.getData('text/plain'));
    if (sourceId && sourceId !== targetId) {
      moveKP(sourceId, targetId);
    }
  };

  const handleDropToRoot = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOverId(null);
    setDraggingId(null);
    const sourceId = Number(e.dataTransfer.getData('text/plain'));
    if (sourceId) {
      moveKP(sourceId, null);
    }
  };

  const renderKPList = (items: TreeKP[], depth = 0): React.ReactNode[] => {
    return items.map(kp => (
      <React.Fragment key={kp.id}>
        <tr
          draggable
          onDragStart={e => handleDragStart(e, kp.id)}
          onDragOver={e => handleDragOver(e, kp.id)}
          onDragLeave={handleDragLeave}
          onDrop={e => handleDrop(e, kp.id)}
          className={`${dragOverId === kp.id ? 'table-primary' : ''} ${draggingId === kp.id ? 'opacity-50' : ''}`}
          style={{ cursor: 'grab' }}
        >
          <td style={{ paddingLeft: `${16 + depth * 24}px` }}>
            <span className="text-muted me-1" style={{ cursor: 'grab' }} title="拖拽移动">
              <i className="bi bi-grip-vertical"></i>
            </span>
            {depth > 0 && <span className="text-muted me-1">└─</span>}
            <strong>{kp.name}</strong>
            {kp.description && <><br /><small className="text-muted">{kp.description}</small></>}
          </td>
          <td><span className="badge bg-info">{kp.question_count || 0}</span></td>
          <td>
            <div className="btn-group btn-group-sm">
              <button className="btn btn-outline-danger" onClick={() => deleteKP(kp.id)} title="删除">
                <i className="bi bi-trash"></i>
              </button>
            </div>
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
            <tbody
              onDragOver={e => { e.preventDefault(); setDragOverId(-1); }}
              onDrop={handleDropToRoot}
              className={dragOverId === -1 ? 'table-primary' : ''}
            >
              {tree.length > 0 ? renderKPList(tree) : (
                <tr><td colSpan={3} className="text-center text-muted">暂无知识点</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <small className="text-muted mt-2 d-block">
        <i className="bi bi-info-circle"></i> 拖拽知识点到目标行可移动为子节点，拖到底部空白处可设为根节点
      </small>

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

      {toast && (
        <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1050 }}>
          <div className="toast show align-items-center text-bg-success border-0" role="alert">
            <div className="d-flex">
              <div className="toast-body"><i className="bi bi-check-circle"></i> {toast}</div>
              <button type="button" className="btn-close btn-close-white me-2 m-auto" onClick={() => setToast('')}></button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
