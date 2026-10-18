/*
TREKMARK ADMIN PAGE - AdminPage.jsx

This file contains the admin-only React interface.
The normal Trekmark site stays in main.jsx.

The admin page is shown at /admin and communicates with the
FastAPI admin endpoints for authentication, submission review,
training_data searches, editing, approval/rejection and migration.
*/
import React, { useEffect, useState } from 'react';
import {
  ArrowRight,
  Camera,
  Check,
  Compass,
  Database,
  LogOut,
  RotateCcw,
  Save,
  Search,
  Shield,
  Trash2,
  X,
} from 'lucide-react';

const API_BASE_URL = 'http://127.0.0.1:8000';

const ADMIN_TOKEN_KEY = 'trekmark_admin_token';

function adminHeaders(token, includeJson = false) {
  const headers = {
    Authorization: `Bearer ${token}`,
  };

  if (includeJson) headers['Content-Type'] = 'application/json';
  return headers;
}

function AdminLogin({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setStatus('Signing in…');

    try {
      const response = await fetch(`${API_BASE_URL}/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Invalid admin username or password.');
      }

      const data = await response.json();
      localStorage.setItem(ADMIN_TOKEN_KEY, data.access_token);
      onLogin(data.access_token);
    } catch (error) {
      setStatus(error.message || 'Could not sign in.');
    }
  };

  return (
    <main className="admin-login-page">
      <div className="admin-login-card">
        <a className="brand admin-login-brand" href="/"><span className="brand-mark"><Compass size={16}/></span>Trekmark</a>
        <div className="admin-login-icon"><Shield size={28}/></div>
        <span className="admin-kicker">Restricted access</span>
        <h1>Admin sign in</h1>
        <p>Review landmark submissions, check categories, and migrate approved entries.</p>

        <form onSubmit={submit} className="admin-login-form">
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {status && <div className="admin-form-status">{status}</div>}
          <button className="primary admin-wide-button" type="submit">Sign in <ArrowRight size={16}/></button>
        </form>

        <a className="admin-back-link" href="/">← Back to Trekmark</a>
      </div>
    </main>
  );
}

function SubmissionEditor({ submission, token, onChanged, compact = false }) {
  const [form, setForm] = useState({
    name: submission.name || '',
    url: submission.url || submission.image_url || '',
    category_name: submission.category_name || '',
    landmark_id: submission.landmark_id ?? '',
    city: submission.city || '',
    state: submission.state || '',
    country: submission.country || '',
    lat: submission.lat ?? '',
    lon: submission.lon ?? '',
  });
  const [working, setWorking] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    setForm({
      name: submission.name || '',
      url: submission.url || submission.image_url || '',
      category_name: submission.category_name || '',
      landmark_id: submission.landmark_id ?? '',
      city: submission.city || '',
      state: submission.state || '',
      country: submission.country || '',
      lat: submission.lat ?? '',
      lon: submission.lon ?? '',
    });
  }, [submission]);

  const change = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const payload = () => ({
    name: form.name.trim(),
    url: form.url.trim(),
    category_name: form.category_name.trim() || null,
    landmark_id: form.landmark_id === '' ? null : Number(form.landmark_id),
    city: form.city.trim() || null,
    state: form.state.trim() || null,
    country: form.country.trim(),
    lat: form.lat === '' ? null : Number(form.lat),
    lon: form.lon === '' ? null : Number(form.lon),
  });

  const request = async (action) => {
    setWorking(action);
    setMessage('');

    try {
      let url = `${API_BASE_URL}/admin/${action}/${submission.id}`;
      let method = 'POST';
      let body;
      let headers = adminHeaders(token);

      if (action === 'approve') {
        headers = adminHeaders(token, true);
        body = JSON.stringify(payload());
      }

      if (action === 'save') {
        url = `${API_BASE_URL}/admin/submission/${submission.id}`;
        method = 'PUT';
        headers = adminHeaders(token, true);
        body = JSON.stringify(payload());
      }

      if (action === 'delete') {
        url = `${API_BASE_URL}/admin/submission/${submission.id}`;
        method = 'DELETE';
      }

      const response = await fetch(url, { method, headers, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Could not ${action} submission.`);

      setMessage(data.message || 'Saved.');
      await onChanged();
    } catch (error) {
      setMessage(error.message || 'Request failed.');
    } finally {
      setWorking('');
    }
  };

  return (
    <article className={`admin-submission-card ${compact ? 'admin-submission-card--compact' : ''}`}>
      <div className="admin-submission-image">
        {form.url ? <img src={form.url} alt={form.name || 'Submitted landmark'} /> : <Camera size={24}/>} 
      </div>

      <div className="admin-submission-content">
        <div className="admin-submission-heading">
          <div>
            <span>Submission #{submission.id}</span>
            <strong>{form.name || 'Unnamed landmark'}</strong>
          </div>
          {submission.status && <span className={`admin-status admin-status--${String(submission.status).toLowerCase()}`}>{submission.status}</span>}
        </div>

        <div className="admin-edit-grid">
          <label>Name<input value={form.name} onChange={(e) => change('name', e.target.value)} /></label>
          <label>Category name<input value={form.category_name} onChange={(e) => change('category_name', e.target.value)} placeholder="Use search panel below" /></label>
          <label>Landmark ID<input type="number" value={form.landmark_id} onChange={(e) => change('landmark_id', e.target.value)} /></label>
          <label>Country<input value={form.country} onChange={(e) => change('country', e.target.value)} /></label>
          <label>City<input value={form.city} onChange={(e) => change('city', e.target.value)} /></label>
          <label>State / region<input value={form.state} onChange={(e) => change('state', e.target.value)} /></label>
          <label>Latitude<input type="number" step="any" value={form.lat} onChange={(e) => change('lat', e.target.value)} /></label>
          <label>Longitude<input type="number" step="any" value={form.lon} onChange={(e) => change('lon', e.target.value)} /></label>
          <label className="admin-edit-grid__wide">Image URL<input value={form.url} onChange={(e) => change('url', e.target.value)} /></label>
        </div>

        <div className="admin-card-actions">
          <button onClick={() => request('approve')} disabled={!!working} className="admin-action admin-action--approve"><Check size={15}/> Approve</button>
          <button onClick={() => request('reject')} disabled={!!working} className="admin-action admin-action--reject"><X size={15}/> Reject</button>
          <button onClick={() => request('save')} disabled={!!working} className="admin-action"><Save size={15}/> Save edits</button>
          <button onClick={() => request('delete')} disabled={!!working} className="admin-action admin-action--danger"><Trash2 size={15}/> Delete</button>
        </div>
        {message && <div className="admin-inline-message">{message}</div>}
      </div>
    </article>
  );
}

function AdminPage() {
  const [token, setToken] = useState(() => localStorage.getItem(ADMIN_TOKEN_KEY) || '');
  const [pending, setPending] = useState([]);
  const [reviewed, setReviewed] = useState([]);
  const [searchText, setSearchText] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');

  const logout = () => {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    setToken('');
  };

  const adminFetch = async (path, options = {}) => {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...adminHeaders(token, options.body !== undefined),
        ...(options.headers || {}),
      },
    });

    if (response.status === 401) {
      logout();
      throw new Error('Your admin session expired. Please sign in again.');
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Admin request failed.');
    return data;
  };

  const loadAdminData = async () => {
    if (!token) return;
    setLoading(true);
    setNotice('');

    try {
      const [pendingData, reviewedData] = await Promise.all([
        adminFetch('/admin/pending'),
        adminFetch('/admin/non-migrated'),
      ]);
      setPending(Array.isArray(pendingData) ? pendingData : pendingData.submissions || []);
      setReviewed(Array.isArray(reviewedData) ? reviewedData : reviewedData.submissions || []);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAdminData();
  }, [token]);

  const searchTraining = async (event) => {
    event.preventDefault();
    if (!searchText.trim()) return;

    try {
      const data = await adminFetch(`/admin/search?name=${encodeURIComponent(searchText.trim())}`);
      setSearchResults(Array.isArray(data) ? data : data.results || []);
    } catch (error) {
      setNotice(error.message);
    }
  };

  const cleanTables = async () => {
    if (!window.confirm('Migrate all currently approved submissions into the destination table?')) return;

    try {
      const data = await adminFetch('/admin/clean', { method: 'POST' });
      setNotice(data.message || 'Approved submissions migrated successfully.');
      await loadAdminData();
    } catch (error) {
      setNotice(error.message);
    }
  };

  if (!token) return <AdminLogin onLogin={setToken} />;

  return (
    <main className="admin-page">
      <nav className="admin-nav">
        <a className="brand" href="/"><span className="brand-mark"><Compass size={16}/></span>Trekmark</a>
        <div className="admin-nav-actions">
          <a href="/">View site</a>
          <button onClick={logout}><LogOut size={15}/> Log out</button>
        </div>
      </nav>

      <div className="admin-shell">
        <header className="admin-header">
          <div>
            <span className="admin-kicker"><Shield size={14}/> Admin workspace</span>
            <h1>Landmark review</h1>
            <p>Review user submissions, correct information, check existing category names, and migrate approved entries when the session is complete.</p>
          </div>
          <button className="admin-clean-button" onClick={cleanTables}><Database size={17}/> Migrate approved submissions</button>
        </header>

        {notice && <div className="admin-notice">{notice}</div>}

        <section className="admin-stats">
          <div><span>Pending</span><strong>{pending.length}</strong></div>
          <div><span>Reviewed / not migrated</span><strong>{reviewed.length}</strong></div>
          <div><span>Database</span><strong>Neon</strong></div>
        </section>

        <section className="admin-panel">
          <div className="admin-panel-heading">
            <div><span>Queue</span><h2>Pending submissions</h2></div>
            <button className="admin-refresh" onClick={loadAdminData}><RotateCcw size={15}/> Refresh</button>
          </div>
          <p className="admin-panel-help">Edit anything that needs correcting, set the category name/landmark ID if needed, then approve or reject the submission.</p>

          <div className="admin-submission-list">
            {loading ? <div className="admin-empty">Loading submissions…</div> : pending.length === 0 ? <div className="admin-empty">No pending submissions.</div> : pending.map((submission) => (
              <SubmissionEditor key={`pending-${submission.id}`} submission={submission} token={token} onChanged={loadAdminData} />
            ))}
          </div>
        </section>

        <section className="admin-panel">
          <div className="admin-panel-heading">
            <div><span>Review buffer</span><h2>Approved / rejected, not migrated</h2></div>
          </div>
          <p className="admin-panel-help">These decisions have not been migrated yet, so you can still correct an accidental approval/rejection or edit the information before the final migration.</p>

          <div className="admin-submission-list admin-submission-list--compact">
            {reviewed.length === 0 ? <div className="admin-empty">No reviewed submissions waiting for migration.</div> : reviewed.map((submission) => (
              <SubmissionEditor key={`reviewed-${submission.id}`} submission={submission} token={token} onChanged={loadAdminData} compact />
            ))}
          </div>
        </section>

        <section className="admin-panel">
          <div className="admin-panel-heading">
            <div><span>Training data lookup</span><h2>Check existing names & categories</h2></div>
          </div>
          <p className="admin-panel-help">Search `training_data` before creating a new category. Existing matches show the name, category, landmark ID and location currently stored in Neon.</p>

          <form className="admin-search" onSubmit={searchTraining}>
            <Search size={18}/>
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Search landmark or place name…" />
            <button type="submit">Search</button>
          </form>

          <div className="admin-search-results">
            {searchResults.map((row, index) => (
              <div className="admin-search-row" key={`${row.landmark_id || row.id || index}-${index}`}>
                <div><span>Name</span><strong>{row.name || '—'}</strong></div>
                <div><span>Category</span><strong>{row.category_name || '—'}</strong></div>
                <div><span>Landmark ID</span><strong>{row.landmark_id ?? '—'}</strong></div>
                <div><span>Location</span><strong>{[row.city, row.state, row.country].filter(Boolean).join(', ') || '—'}</strong></div>
              </div>
            ))}
            {searchText && searchResults.length === 0 && <div className="admin-empty">No search results yet.</div>}
          </div>
        </section>
      </div>
    </main>
  );
}


export default AdminPage;
