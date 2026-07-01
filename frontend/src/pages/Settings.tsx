import { useEffect, useState } from 'react';
import { api } from '../api';

interface Settings {
  ai_provider: string;
  api_key: string;
  api_url: string;
  ai_model: string;
  has_api_key: boolean;
}

const PROVIDERS = [
  { id: 'deepseek', name: 'DeepSeek', url: 'https://api.deepseek.com/chat/completions', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1/chat/completions', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'] },
  { id: 'custom', name: '自定义', url: '', models: [] },
];

export default function Settings() {
  const [settings, setSettings] = useState<Settings>({
    ai_provider: 'deepseek', api_key: '', api_url: '', ai_model: 'deepseek-chat', has_api_key: false,
  });
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [toast, setToast] = useState('');

  useEffect(() => {
    api.getSettings().then(d => {
      const s = d as unknown as Settings;
      setSettings(s);
    });
  }, []);

  const provider = PROVIDERS.find(p => p.id === settings.ai_provider) || PROVIDERS[0];

  const handleProviderChange = (id: string) => {
    const p = PROVIDERS.find(pp => pp.id === id);
    if (p) {
      setSettings({
        ...settings,
        ai_provider: id,
        api_url: p.url,
        ai_model: p.models[0] || '',
      });
    } else {
      setSettings({ ...settings, ai_provider: id });
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, string> = {
        ai_provider: settings.ai_provider,
        api_url: settings.api_url,
        ai_model: settings.ai_model,
      };
      if (settings.api_key) payload.api_key = settings.api_key;
      await api.saveSettings(payload);
      setToast('设置已保存');
      setTimeout(() => setToast(''), 3000);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // Save first if there's a new key
      if (settings.api_key) {
        await api.saveSettings({ api_key: settings.api_key, api_url: settings.api_url, ai_model: settings.ai_model, ai_provider: settings.ai_provider });
      }
      const result = await api.testSettings() as { success: boolean; message?: string; error?: string };
      setTestResult({ ok: result.success, msg: result.success ? result.message! : result.error! });
    } catch (e) {
      setTestResult({ ok: false, msg: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      <h4 className="mb-4"><i className="bi bi-gear"></i> 设置</h4>

      <div className="row">
        <div className="col-lg-8">
          <div className="card mb-4">
            <div className="card-header"><i className="bi bi-robot"></i> AI 分析配置</div>
            <div className="card-body">
              <div className="mb-3">
                <label className="form-label fw-bold">AI 服务商</label>
                <div className="d-flex gap-2 flex-wrap">
                  {PROVIDERS.map(p => (
                    <button key={p.id}
                      className={`btn ${settings.ai_provider === p.id ? 'btn-primary' : 'btn-outline-primary'}`}
                      onClick={() => handleProviderChange(p.id)}>
                      {p.name}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mb-3">
                <label className="form-label fw-bold">API Key <span className="text-danger">*</span></label>
                <div className="input-group">
                  <input type={showKey ? 'text' : 'password'}
                    className="form-control"
                    placeholder={settings.has_api_key ? '已配置（留空保持不变）' : '输入 API Key...'}
                    value={settings.api_key}
                    onChange={e => setSettings({ ...settings, api_key: e.target.value })} />
                  <button className="btn btn-outline-secondary" onClick={() => setShowKey(!showKey)}>
                    <i className={`bi ${showKey ? 'bi-eye-slash' : 'bi-eye'}`}></i>
                  </button>
                </div>
                <div className="form-text">
                  {settings.ai_provider === 'deepseek' && (
                    <>前往 <a href="https://platform.deepseek.com/" target="_blank" rel="noreferrer">platform.deepseek.com</a> 获取 API Key</>
                  )}
                  {settings.ai_provider === 'openai' && (
                    <>前往 <a href="https://platform.openai.com/" target="_blank" rel="noreferrer">platform.openai.com</a> 获取 API Key</>
                  )}
                </div>
              </div>

              <div className="mb-3">
                <label className="form-label fw-bold">模型</label>
                {provider.models.length > 0 ? (
                  <select className="form-select" value={settings.ai_model}
                    onChange={e => setSettings({ ...settings, ai_model: e.target.value })}>
                    {provider.models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input type="text" className="form-control" placeholder="输入模型名称..."
                    value={settings.ai_model} onChange={e => setSettings({ ...settings, ai_model: e.target.value })} />
                )}
              </div>

              <div className="mb-3">
                <label className="form-label fw-bold">API 地址</label>
                <input type="text" className="form-control" placeholder="https://api.example.com/chat/completions"
                  value={settings.api_url} onChange={e => setSettings({ ...settings, api_url: e.target.value })} />
                <div className="form-text">通常不需要修改，除非使用自定义端点或代理</div>
              </div>

              <hr />
              <div className="d-flex gap-2">
                <button className="btn btn-primary" onClick={save} disabled={saving}>
                  {saving ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-check-circle"></i>} 保存设置
                </button>
                <button className="btn btn-outline-success" onClick={test} disabled={testing}>
                  {testing ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-lightning"></i>} 测试连接
                </button>
              </div>

              {testResult && (
                <div className={`alert ${testResult.ok ? 'alert-success' : 'alert-danger'} mt-3 mb-0`}>
                  {testResult.ok ? <i className="bi bi-check-circle"></i> : <i className="bi bi-x-circle"></i>}
                  {' '}{testResult.msg}
                </div>
              )}
            </div>
          </div>

          <div className="card mb-4">
            <div className="card-header"><i className="bi bi-info-circle"></i> 说明</div>
            <div className="card-body text-muted small">
              <p className="mb-2">AI 分析功能会将题目内容发送到所选服务商的 API，自动识别知识点并生成标签。</p>
              <p className="mb-2">支持的 AI 服务商：</p>
              <ul className="mb-2">
                <li><strong>DeepSeek</strong> — 国产大模型，性价比高，推荐使用</li>
                <li><strong>OpenAI</strong> — GPT 系列，需要海外网络</li>
                <li><strong>自定义</strong> — 任何兼容 OpenAI 接口格式的服务</li>
              </ul>
              <p className="mb-0">API Key 仅存储在本地数据库中，不会上传到任何第三方。</p>
            </div>
          </div>
        </div>

        <div className="col-lg-4">
          <div className="card">
            <div className="card-header"><i className="bi bi-list-check"></i> 当前状态</div>
            <div className="card-body">
              <table className="table table-sm mb-0">
                <tbody>
                  <tr><td className="text-muted">服务商</td><td><span className="badge bg-primary">{provider.name}</span></td></tr>
                  <tr><td className="text-muted">模型</td><td><code>{settings.ai_model || '-'}</code></td></tr>
                  <tr><td className="text-muted">API Key</td><td>{settings.has_api_key ? <span className="badge bg-success">已配置</span> : <span className="badge bg-warning text-dark">未配置</span>}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

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
