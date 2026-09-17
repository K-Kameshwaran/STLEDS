import { useState, useEffect } from 'react';
import { 
  Shield, 
  Lock, 
  Key, 
  FileText, 
  Eye, 
  CheckCircle, 
  UploadCloud, 
  Download, 
  Terminal, 
  LogOut,
  AlertCircle,
  FileCheck,
  Server,
  Activity
} from 'lucide-react';
import './App.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [role, setRole] = useState<string | null>(localStorage.getItem('role'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('pass');
  const [mfaCode, setMfaCode] = useState('123456');
  
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // App State
  const [paperId, setPaperId] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [viewerBlobUrl, setViewerBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (token && !role) {
      try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const pad = base64.length % 4;
        const paddedBase64 = pad ? base64 + '='.repeat(4 - pad) : base64;
        const payload = JSON.parse(atob(paddedBase64));
        setRole(payload.role);
        localStorage.setItem('role', payload.role);
      } catch (e) {
        console.error("Invalid token");
      }
    }
  }, [token, role]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Bypass-Tunnel-Reminder': 'true' },
        body: JSON.stringify({ email, password, mfa_code: mfaCode })
      });
      if (!response.ok) {
        const errText = await response.text();
        console.error("Backend Error Response:", response.status, errText);
        throw new Error("Login Failed. Check credentials.");
      }
      const data = await response.json();
      setToken(data.access_token);
      localStorage.setItem('token', data.access_token);
      
      const base64Url = data.access_token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const pad = base64.length % 4;
      const paddedBase64 = pad ? base64 + '='.repeat(4 - pad) : base64;
      const payload = JSON.parse(atob(paddedBase64));
      setRole(payload.role);
      localStorage.setItem('role', payload.role);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setRole(null);
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setPaperId(null);
    setSessionId(null);
    setSelectedFile(null);
    setError('');
    setMessage('');
  };

  const uploadPaper = async () => {
    if (!selectedFile) return setError("Please select a file first.");
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('title', 'Exam Paper: ' + selectedFile.name);
      formData.append('exam_id', '1');
      formData.append('file', selectedFile);

      const response = await fetch(`${API_URL}/exams/papers`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' },
        body: formData
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setPaperId(data.paper_id);
      setMessage(`Upload Successful! Generated Paper ID: ${data.paper_id}`);
    } catch(err: any) {
      setError("Upload Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const viewPaper = async () => {
    if (!paperId) return setError("Please enter a valid Paper ID to view");
    setError(''); setMessage(''); setLoading(true); setViewerBlobUrl(null);
    try {
      const res = await fetch(`${API_URL}/exams/papers/${paperId}/view`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      setViewerBlobUrl(url);
      setMessage(`Paper ${paperId} loaded securely into viewer.`);
    } catch(err: any) {
      setError("View Error: " + err.message);
    } finally { setLoading(false); }
  };

  const approvePaper = async () => {
    if (!paperId) return setError("Please enter a valid Paper ID");
    setError(''); setMessage(''); setLoading(true);
    try {
      let res = await fetch(`${API_URL}/exams/papers/${paperId}/status?new_status=PENDING_REVIEW`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error("PENDING_REVIEW transition failed: " + await res.text());

      res = await fetch(`${API_URL}/exams/papers/${paperId}/status?new_status=APPROVED`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage(`Success! Paper ${paperId} has been APPROVED.`);
    } catch(err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const lockPaper = async () => {
    if (!paperId) return setError("Please enter a valid Paper ID");
    setError(''); setMessage(''); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/exams/papers/${paperId}/status?new_status=LOCKED`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage(`Success! Paper ${paperId} is now LOCKED for Release.`);
    } catch(err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  };

  const createReleaseSession = async () => {
    setError(''); setMessage(''); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/release/sessions`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Bypass-Tunnel-Reminder': 'true'
        },
        body: JSON.stringify({ exam_id: 1 })
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(data.session_id);
      setMessage(`Release Session Created Successfully! Session ID: ${data.session_id}`);
    } catch(err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  };

  const authorizeReleaseSession = async () => {
    if (!sessionId) return setError("Please enter an active Session ID");
    setError(''); setMessage(''); setLoading(true);
    try {
      const timestamp = new Date().toISOString();
      const res = await fetch(`${API_URL}/release/sessions/${sessionId}/authorize`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Bypass-Tunnel-Reminder': 'true'
        },
        body: JSON.stringify({ client_timestamp: timestamp })
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage(`Session ${sessionId} successfully authorized by ${role}.`);
    } catch(err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  };

  const executeReleaseSession = async () => {
    if (!sessionId) return setError("Please enter an active Session ID");
    setError(''); setMessage(''); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/release/sessions/${sessionId}/execute`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Bypass-Tunnel-Reminder': 'true'
        }
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage(`Session ${sessionId} EXECUTED. Papers are now Released!`);
    } catch(err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  };

  const downloadPaper = async () => {
    if (!paperId) return setError("Please enter a valid Paper ID to download");
    setError(''); setMessage(''); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/exams/papers/${paperId}/download`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `watermarked_paper_${paperId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setMessage(`Successfully downloaded watermarked Paper ${paperId}`);
    } catch(err: any) {
      setError("Download Error: " + err.message);
    } finally { setLoading(false); }
  };

  const verifyAudit = async () => {
    setError(''); setMessage(''); setLoading(true);
    try {
      const res = await fetch(`${API_URL}/audit/verify`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}`, 'Bypass-Tunnel-Reminder': 'true' }
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data.valid) {
        setMessage(`Audit Verification Successful. Chain is cryptographically valid.`);
      } else {
        setError(`ALERT: Audit Chain Tampering Detected! Verification failed.`);
      }
    } catch(err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  };

  if (!token) {
    return (
      <div className="app-container">
        <div className="login-view">
          <div className="login-card">
            <div className="login-header">
              <div className="logo-wrapper">
                <Shield size={32} />
              </div>
              <h1>STLEDS</h1>
              <p>Secure Examination Delivery System</p>
            </div>
            <form onSubmit={handleLogin}>
              <div className="form-group">
                <label className="form-label">Identity (Email)</label>
                <input 
                  className="form-input"
                  value={email} 
                  onChange={e => setEmail(e.target.value)} 
                  placeholder="name@domain.com" 
                  type="email" 
                  required 
                />
              </div>
              <div className="form-group">
                <label className="form-label">Password</label>
                <input 
                  className="form-input"
                  value={password} 
                  onChange={e => setPassword(e.target.value)} 
                  placeholder="••••••••" 
                  type="password" 
                  required 
                />
              </div>
              <div className="form-group">
                <label className="form-label">MFA Token (TOTP)</label>
                <input 
                  className="form-input"
                  value={mfaCode} 
                  onChange={e => setMfaCode(e.target.value)} 
                  placeholder="6-digit code" 
                  required 
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <span className="spinner"><Activity size={18} /></span> : <><Lock size={18} /> Authenticate Securely</>}
              </button>
            </form>
            {error && (
              <div className="alert alert-error" style={{marginTop: '1.5rem', marginBottom: 0}}>
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container dashboard-layout">
      <header className="topbar">
        <div className="topbar-brand">
          <Shield size={28} className="logo-icon" />
          <h2>STLEDS <span style={{fontWeight: 400, color: 'var(--text-secondary)'}}>| Command Center</span></h2>
        </div>
        <div className="topbar-user">
          <div className="role-badge">
            <Key size={14} /> {role}
          </div>
          <button className="btn btn-secondary" onClick={handleLogout}>
            <LogOut size={16} /> Logout
          </button>
        </div>
      </header>
      
      <main className="main-content">
        {error && (
          <div className="alert alert-error">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}
        {message && (
          <div className="alert alert-success">
            <CheckCircle size={18} />
            <span>{message}</span>
          </div>
        )}

        <div className="context-header">
          <div className="form-group context-field">
            <label className="form-label">Target Paper ID</label>
            <input 
              className="form-input" 
              type="number" 
              placeholder="e.g. 20" 
              value={paperId || ''} 
              onChange={e => setPaperId(Number(e.target.value))} 
            />
          </div>
          <div className="form-group context-field">
            <label className="form-label">Active Session ID</label>
            <input 
              className="form-input" 
              type="number" 
              placeholder="e.g. 1" 
              value={sessionId || ''} 
              onChange={e => setSessionId(Number(e.target.value))} 
            />
          </div>
        </div>

        <div className="grid-layout">
          
          {role === 'QUESTION_SETTER' && (
            <div className="card col-span-full">
              <div className="card-header">
                <div className="card-icon"><UploadCloud size={24} /></div>
                <div>
                  <h3 className="card-title">Document Ingestion</h3>
                </div>
              </div>
              <p className="card-description">Select a PDF draft to securely upload to the STLEDS encrypted vault.</p>
              
              <div className="upload-zone" onClick={() => document.getElementById('file-upload')?.click()}>
                <div className="upload-zone-content">
                  <FileText size={48} className="upload-icon" />
                  <p>{selectedFile ? selectedFile.name : "Click to Browse or Drag & Drop PDF"}</p>
                </div>
                <input 
                  type="file" 
                  id="file-upload" 
                  accept="application/pdf"
                  onChange={e => setSelectedFile(e.target.files ? e.target.files[0] : null)}
                  className="file-input"
                />
              </div>
              <div style={{marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end'}}>
                <button className="btn btn-primary" onClick={uploadPaper} disabled={loading || !selectedFile} style={{width: 'auto'}}>
                  {loading ? "Uploading..." : <><Lock size={18} /> Commit to Vault</>}
                </button>
              </div>
            </div>
          )}

          {role === 'REVIEWER' && (
            <div className="card col-span-full">
              <div className="card-header">
                <div className="card-icon"><Eye size={24} /></div>
                <div>
                  <h3 className="card-title">Review & Approve Question Paper</h3>
                </div>
              </div>
              <p className="card-description">Review the selected question paper in the secure viewer below before approving.</p>
              
              <div className="process-steps">
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 1</h4>
                    <h3>Load Document</h3>
                  </div>
                  <button className="btn btn-secondary" onClick={viewPaper} disabled={loading || !paperId}>
                    <Eye size={18} /> Secure Preview
                  </button>
                </div>
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 2</h4>
                    <h3>Validation</h3>
                  </div>
                  <button className="btn btn-primary" onClick={approvePaper} disabled={loading || !viewerBlobUrl}>
                    <FileCheck size={18} /> Approve Document
                  </button>
                </div>
              </div>

              {viewerBlobUrl && (
                <div className="secure-viewer">
                  <div className="viewer-banner">
                    <Shield size={16} />
                    <span>SECURE IN-APP VIEWER - ORIGINAL DOWNLOAD RESTRICTED</span>
                  </div>
                  <object data={viewerBlobUrl} type="application/pdf" className="pdf-object">
                    <p style={{padding: '2rem'}}>Browser does not support embedded PDFs. Download restricted.</p>
                  </object>
                </div>
              )}
            </div>
          )}

          {role === 'EXAM_CONTROLLER' && (
            <div className="card col-span-full">
              <div className="card-header">
                <div className="card-icon"><Server size={24} /></div>
                <div>
                  <h3 className="card-title">Release Controller Operations</h3>
                </div>
              </div>
              <p className="card-description">Initiate and execute the strict dual-custodian release workflow.</p>
              
              <div className="process-steps">
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 1</h4>
                    <h3>Lock Target</h3>
                  </div>
                  <button className="btn btn-secondary" onClick={lockPaper} disabled={loading}>
                    <Lock size={18} /> Lock Paper
                  </button>
                </div>
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 2</h4>
                    <h3>Initialization</h3>
                  </div>
                  <button className="btn btn-secondary" onClick={createReleaseSession} disabled={loading}>
                    <Activity size={18} /> Create Session
                  </button>
                </div>
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 3</h4>
                    <h3>1st Signature</h3>
                  </div>
                  <button className="btn btn-primary" onClick={authorizeReleaseSession} disabled={loading}>
                    <Key size={18} /> Sign & Authorize
                  </button>
                </div>
                <div className="step-card">
                  <div className="step-header">
                    <h4>Step 4</h4>
                    <h3>Final Execution</h3>
                  </div>
                  <button className="btn btn-danger" onClick={executeReleaseSession} disabled={loading}>
                    <Server size={18} /> Execute Release
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {role === 'EXTERNAL_OBSERVER' && (
            <div className="card">
              <div className="card-header">
                <div className="card-icon"><Key size={24} /></div>
                <div>
                  <h3 className="card-title">Observer Authorization</h3>
                </div>
              </div>
              <p className="card-description">Provide your independent cryptographic authorization for the active release session.</p>
              <button className="btn btn-primary" onClick={authorizeReleaseSession} disabled={loading}>
                <Key size={18} /> Co-Authorize Session
              </button>
            </div>
          )}

          {role === 'CENTER_SUPERINTENDENT' && (
            <div className="card">
              <div className="card-header">
                <div className="card-icon"><Download size={24} /></div>
                <div>
                  <h3 className="card-title">Secure Delivery</h3>
                </div>
              </div>
              <p className="card-description">Download a cryptographically watermarked copy of the released paper.</p>
              <button className="btn btn-primary" onClick={downloadPaper} disabled={loading}>
                <Download size={18} /> Download Watermarked Paper
              </button>
            </div>
          )}

          {role === 'AUDITOR' && (
            <div className="card">
              <div className="card-header">
                <div className="card-icon"><Terminal size={24} /></div>
                <div>
                  <h3 className="card-title">Compliance Audit</h3>
                </div>
              </div>
              <p className="card-description">Verify the cryptographic integrity of the entire examination event timeline.</p>
              <button className="btn btn-secondary" onClick={verifyAudit} disabled={loading}>
                <Shield size={18} /> Verify Audit Chain
              </button>
            </div>
          )}

          {/* Security Status Sidebar */}
          <div className="card">
            <div className="card-header">
              <div className="card-icon"><Shield size={24} /></div>
              <div>
                <h3 className="card-title">System Status</h3>
              </div>
            </div>
            <ul className="status-list">
              <li className="status-item">
                <div className="status-indicator status-success"><CheckCircle size={20} /></div>
                <div className="status-text">
                  <h4>Identity Verified</h4>
                  <p>MFA enforced context active</p>
                </div>
              </li>
              <li className="status-item">
                <div className="status-indicator status-success"><CheckCircle size={20} /></div>
                <div className="status-text">
                  <h4>AES-256-GCM</h4>
                  <p>Data encrypted in transit & at rest</p>
                </div>
              </li>
              <li className="status-item">
                <div className="status-indicator status-success"><CheckCircle size={20} /></div>
                <div className="status-text">
                  <h4>Audit Chain</h4>
                  <p>Cryptographic ledger logging active</p>
                </div>
              </li>
            </ul>
          </div>

        </div>
      </main>
    </div>
  );
}
