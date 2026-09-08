import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import type { ImportTask, PdfImportQuestion } from '../types';

const STEP_LABELS: Record<string, string> = {
  mineru: 'PDF 解析 (MinerU)',
  normalize: '文档规范化',
  detect: '题目检测 (规则引擎)',
  llm_split: '题目识别 (AI)',
  split: '题目切分',
  ocr_repair: 'OCR 修复',
  enrich: 'AI 知识点提取',
  merge: '合并结果',
  visual_recovery: '视觉复判',
  page_enrich: '本页知识点提取',
  page_import: '本页录入题库',
};

function formatElapsed(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m${s}s`;
}

/** Render LaTeX in text to HTML using KaTeX. */
function renderLatex(text: string): string {
  if (!text) return '';
  const esc = (t: string) =>
    t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const parts: string[] = [];
  let remaining = text;
  const re = /\$\$(.+?)\$\$|\$(.+?)\$/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(remaining)) !== null) {
    if (m.index > lastIdx) parts.push(esc(remaining.slice(lastIdx, m.index)));
    const tex = decodeURIComponent(m[1] ?? m[2]);
    const display = m[1] !== undefined;
    try {
      parts.push(katex.renderToString(tex, { displayMode: display, throwOnError: false }));
    } catch {
      parts.push(esc(tex));
    }
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < remaining.length) parts.push(esc(remaining.slice(lastIdx)));
  return parts.join('');
}

// ── Upload Phase ─────────────────────────────────────────────

function UploadPhase({ onStart }: { onStart: (file: File, autoImport: boolean) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [autoImport, setAutoImport] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.toLowerCase().endsWith('.pdf')) setFile(f);
  };

  return (
    <div className="card">
      <div className="card-body">
        <h5 className="card-title"><i className="bi bi-file-earmark-pdf"></i> PDF 导入</h5>
        <p className="text-muted">上传考研试卷 PDF，系统将自动提取题目并分析知识点。</p>

        <div
          className={`border border-2 border-dashed rounded p-5 text-center mb-3 ${dragOver ? 'border-primary bg-light' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          style={{ cursor: 'pointer' }}
        >
          <input ref={inputRef} type="file" accept=".pdf" hidden onChange={e => {
            const f = e.target.files?.[0];
            if (f) setFile(f);
          }} />
          {file ? (
            <div>
              <i className="bi bi-file-earmark-pdf fs-1 text-danger"></i>
              <p className="mb-1 fw-bold">{file.name}</p>
              <p className="text-muted">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
            </div>
          ) : (
            <div>
              <i className="bi bi-cloud-upload fs-1 text-muted"></i>
              <p className="mb-0">点击或拖拽上传 PDF</p>
            </div>
          )}
        </div>

        <div className="form-check mb-3">
          <input
            className="form-check-input"
            type="checkbox"
            id="autoImport"
            checked={autoImport}
            onChange={e => setAutoImport(e.target.checked)}
          />
          <label className="form-check-label" htmlFor="autoImport">
            逐页处理并自动录入题库
          </label>
        </div>

        <button
          className="btn btn-primary"
          disabled={!file}
          onClick={() => file && onStart(file, autoImport)}
        >
          <i className="bi bi-play"></i> 开始导入
        </button>
      </div>
    </div>
  );
}

// ── Progress Phase ────────────────────────────────────────────

function ProgressPhase({ task, onFailed }: { task: ImportTask; onFailed: () => void }) {
  const label = STEP_LABELS[task.current_step] || task.current_step;

  return (
    <div className="card">
      <div className="card-body">
        <h5 className="card-title">
          {task.status !== 'failed' && <span className="spinner-border spinner-border-sm me-2" />}
          {task.status === 'failed' ? '处理失败' : '正在处理'}: {task.pdf_name}
        </h5>

        <div className="progress mb-3" style={{ height: '24px' }}>
          <div
            className={`progress-bar ${task.status === 'failed' ? 'bg-danger' : 'progress-bar-striped progress-bar-animated'}`}
            style={{ width: `${task.progress}%` }}
          >
            {task.progress}%
          </div>
        </div>

        <table className="table table-sm">
          <tbody>
            <tr><td className="text-muted" style={{width:120}}>当前步骤</td><td>{label}</td></tr>
            {task.total_questions > 0 && (
              <tr><td className="text-muted">处理进度</td><td>{task.current_question} / {task.total_questions} 题</td></tr>
            )}
            <tr><td className="text-muted">已耗时</td><td>{formatElapsed(task.elapsed_seconds)}</td></tr>
          </tbody>
        </table>

        {task.status === 'failed' && (
          <div className="alert alert-danger">
            <strong>处理失败：</strong> {task.error_message || '未知错误'}
            <div className="mt-2">
              <button className="btn btn-outline-secondary btn-sm" onClick={onFailed}>返回</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Source Input Component ────────────────────────────────────

function SourceInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [sources, setSources] = useState<string[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.sources().then(d => setSources(d as string[])).catch(() => {});
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="input-group" ref={dropdownRef}>
      <input
        type="text"
        className="form-control"
        placeholder="例如：2024年真题、教材第一章"
        value={value}
        onChange={e => onChange(e.target.value)}
      />
      {sources.length > 0 && (
        <button
          className="btn btn-outline-secondary dropdown-toggle"
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
        >
          <i className="bi bi-clock-history"></i>
        </button>
      )}
      {showDropdown && sources.length > 0 && (
        <ul className="dropdown-menu dropdown-menu-end show" style={{ position: 'absolute', zIndex: 1050 }}>
          <li><h6 className="dropdown-header">历史来源</h6></li>
          {sources.map(s => (
            <li key={s}>
              <button className="dropdown-item" onClick={() => { onChange(s); setShowDropdown(false); }}>
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Result Phase ──────────────────────────────────────────────

function ResultPhase({ taskId, autoImport, onBack }: { taskId: string; autoImport: boolean; onBack: () => void }) {
  const [questions, setQuestions] = useState<PdfImportQuestion[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<string | null>(null);
  const [source, setSource] = useState('');

  useEffect(() => {
    api.getTaskResult(taskId)
      .then(data => {
        const qs = (data.questions as PdfImportQuestion[]) || [];
        setQuestions(qs);
        // Pre-fill source from first question if available
        if (qs.length > 0 && qs[0].source) {
          setSource(qs[0].source);
        }
      })
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [taskId]);

  const handleImport = async () => {
    setImporting(true);
    try {
      const data = await api.getTaskResult(taskId);
      // Apply source to all questions
      if (source && data.questions) {
        (data.questions as PdfImportQuestion[]).forEach(q => { q.source = source; });
      }
      const result = await api.importFromTask(data as Record<string, unknown>);
      setImportResult(result.message || '导入成功');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setImporting(false);
    }
  };

  if (loading) return <div className="text-center p-5"><span className="spinner-border" /></div>;
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!questions.length) return <div className="alert alert-warning">没有提取到题目。</div>;

  if (autoImport) {
    return (
      <div className="card">
        <div className="card-body text-center py-5">
          <i className="bi bi-check-circle text-success fs-1"></i>
          <h5 className="mt-3">已按页自动录入 {questions.length} 道题</h5>
          <p className="text-muted">每页题目完成知识点提取和复判后已写入题库</p>
          <div className="d-flex gap-2 justify-content-center">
            <button className="btn btn-primary" onClick={onBack}>继续导入</button>
            <a href="/questions" className="btn btn-outline-primary">查看题目列表</a>
          </div>
        </div>
      </div>
    );
  }

  if (importResult) {
    return (
      <div className="card">
        <div className="card-body text-center py-5">
          <i className="bi bi-check-circle text-success fs-1"></i>
          <h5 className="mt-3">{importResult}</h5>
          <p className="text-muted">题目已成功导入到题库中</p>
          <div className="d-flex gap-2 justify-content-center">
            <button className="btn btn-primary" onClick={onBack}>继续导入</button>
            <a href="/questions" className="btn btn-outline-primary">查看题目列表</a>
          </div>
        </div>
      </div>
    );
  }

  const q = questions[idx];

  return (
    <div className="card">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h5 className="card-title mb-0">提取结果：{questions.length} 题</h5>
          <button className="btn btn-outline-secondary btn-sm" onClick={onBack}>
            <i className="bi bi-arrow-left"></i> 重新导入
          </button>
        </div>

        {/* Source input */}
        <div className="mb-3">
          <label className="form-label fw-bold">
            <i className="bi bi-tag"></i> 来源
            <small className="text-muted fw-normal ms-2">所有题目共用此来源</small>
          </label>
          <SourceInput value={source} onChange={setSource} />
        </div>

        <div className="border rounded p-3 mb-3">
          <div className="d-flex justify-content-between mb-2">
            <span className="badge bg-info">第 {idx + 1} / {questions.length} 题</span>
            <span className="badge bg-secondary">{q.subject_name}</span>
          </div>

          <div className="mb-3" style={{ fontFamily: 'serif', lineHeight: 1.8 }}
            dangerouslySetInnerHTML={{ __html: renderLatex(q.content) }}
          />

          <h6>知识点</h6>
          {q.knowledge_points.map((kp, i) => (
            <span key={i} className={`badge me-1 mb-1 ${kp.role === 'primary' ? 'bg-primary' : 'bg-outline-secondary text-dark border'}`}>
              {kp.name}
              <small className="ms-1">({kp.role === 'primary' ? '主要' : '次要'}, {kp.weight})</small>
            </span>
          ))}

          {q.source && (
            <p className="text-muted mt-2 mb-0">
              <small>
                来源: {q.source}
                {q.source_page ? `，第 ${q.source_page} 页` : ''}
                {q.needs_review ? <span className="badge bg-warning text-dark ms-2">待复核</span> : null}
              </small>
            </p>
          )}
        </div>

        <div className="d-flex justify-content-between mb-3">
          <button className="btn btn-outline-primary" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
            <i className="bi bi-chevron-left"></i> 上一题
          </button>
          <span className="text-muted align-self-center">{idx + 1} / {questions.length}</span>
          <button className="btn btn-outline-primary" disabled={idx >= questions.length - 1} onClick={() => setIdx(idx + 1)}>
            下一题 <i className="bi bi-chevron-right"></i>
          </button>
        </div>

        <hr />
        <div className="text-center">
          <button className="btn btn-success btn-lg" onClick={handleImport} disabled={importing}>
            {importing ? (
              <><span className="spinner-border spinner-border-sm me-2"></span>导入中...</>
            ) : (
              <><i className="bi bi-download me-2"></i>导入全部 {questions.length} 题到题库</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────

type Phase = 'upload' | 'pending' | 'running' | 'result';

export default function PdfImport() {
  const [phase, setPhase] = useState<Phase>('upload');
  const [task, setTask] = useState<ImportTask | null>(null);
  const [taskId, setTaskId] = useState('');
  const [autoImport, setAutoImport] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollTask = useCallback((tid: string) => {
    const poll = async () => {
      try {
        const data = (await api.getTask(tid)) as unknown as ImportTask;
        setTask(data);
        if (data.status === 'completed') {
          stopPolling();
          setPhase('result');
        } else if (data.status === 'failed') {
          stopPolling();
        } else {
          setPhase('running');
        }
      } catch { /* ignore polling errors */ }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleStart = async (file: File, useAutoImport: boolean) => {
    try {
      setAutoImport(useAutoImport);
      const result = await api.pdfImport(file, undefined, useAutoImport);
      setTaskId(result.task_id);
      setPhase('pending');
      pollTask(result.task_id);
    } catch (e) {
      alert((e as Error).message);
    }
  };

  const handleBack = () => {
    stopPolling();
    setPhase('upload');
    setTask(null);
    setTaskId('');
  };

  return (
    <>
      <h4 className="mb-3"><i className="bi bi-file-earmark-pdf"></i> PDF 导入</h4>

      {phase === 'upload' && <UploadPhase onStart={handleStart} />}
      {(phase === 'pending' || phase === 'running') && task && <ProgressPhase task={task} onFailed={handleBack} />}
      {phase === 'result' && <ResultPhase taskId={taskId} autoImport={autoImport} onBack={handleBack} />}
    </>
  );
}
