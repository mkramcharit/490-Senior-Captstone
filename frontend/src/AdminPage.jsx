/*
TREKMARK ADMIN PAGE - AdminPage.jsx

This file contains the admin-only React interface.
The normal Trekmark site stays in main.jsx.

The admin page is shown at /admin and communicates with the
FastAPI admin endpoints for authentication, submission review,
training_data searches, editing, approval/rejection and migration.
*/
import React, { useEffect, useState } from 'react';
import { AdminAccess, apiErrorMessage } from './AccountPanel.jsx';
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;

const ADMIN_TOKEN_KEY = 'trekmark_admin_token';

function adminHeaders(token, includeJson = false) {
  const headers = {
    Authorization: `Bearer ${token}`,
  };

  if (includeJson) headers['Content-Type'] = 'application/json';
  return headers;
}

// Preview the same canonical format enforced by the backend.
function formatCategory(value) {
  const words = String(value || '').normalize('NFKC').trim().replace(/^(?:category\s*:\s*)+/i, '').split(/[\s_]+/).filter(Boolean);
  return words.length ? 'Category:' + words.map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()).join('_') : '';
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
    category_name: formatCategory(form.category_name) || null,
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
    if (action === 'approve' && !formatCategory(form.category_name)) {
      setMessage('Enter a category before approving.'); setWorking(''); return;
    }

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
      if (!response.ok) throw new Error(apiErrorMessage(data, `Could not ${action} submission.`));

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
          <label>Category name<input value={form.category_name} onChange={(e) => change('category_name', e.target.value)} onBlur={() => change('category_name', formatCategory(form.category_name))} placeholder="historic monuments" />
            <small>Saved as: {formatCategory(form.category_name) || 'Category:Historic_Monuments'}</small></label>
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

  if (!token) return <AdminAccess />;

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


// Keep admin styles in this component so the login page has no separate
// stylesheet dependency to resolve when copying the replacement file.
const ADMIN_STYLES = "/* ADMIN PAGE */\n.admin-page,.admin-login-page{min-height:100vh;background:radial-gradient(circle at 10% 10%,rgba(54,112,174,.18),transparent 28%),linear-gradient(180deg,#07101d,#0c1b2c 62%,#10253a);color:#f5f7fb}.admin-login-page{display:grid;place-items:center;padding:40px 20px}.admin-login-card{width:min(460px,100%);padding:36px;border:1px solid rgba(255,255,255,.11);border-radius:28px;background:rgba(7,14,24,.9);box-shadow:0 32px 110px rgba(0,0,0,.45)}.admin-login-brand{display:inline-flex;margin-bottom:34px}.admin-login-icon{width:58px;height:58px;border-radius:18px;display:grid;place-items:center;background:rgba(126,207,255,.1);color:#8ed8ff;border:1px solid rgba(126,207,255,.18);margin-bottom:18px}.admin-kicker{display:flex;align-items:center;gap:7px;color:#8ed8ff;text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:700}.admin-login-card h1{font-size:42px;letter-spacing:-.04em;margin:10px 0}.admin-login-card>p{color:#98a5b5;line-height:1.6}.admin-login-form{display:grid;gap:16px;margin-top:26px}.admin-login-form label,.admin-edit-grid label{display:grid;gap:7px;color:#9eabbc;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.admin-login-form input,.admin-edit-grid input,.admin-search input{width:100%;border:1px solid rgba(255,255,255,.11);background:rgba(255,255,255,.045);color:#fff;border-radius:12px;padding:13px 14px;outline:none}.admin-login-form input:focus,.admin-edit-grid input:focus,.admin-search input:focus{border-color:rgba(126,207,255,.55);box-shadow:0 0 0 3px rgba(126,207,255,.08)}.admin-form-status,.admin-inline-message{font-size:12px;color:#f4be86}.admin-wide-button{width:100%;justify-content:center}.admin-back-link{display:block;text-align:center;color:#8997a8;font-size:12px;margin-top:20px;text-decoration:none}.admin-nav{height:72px;display:flex;align-items:center;justify-content:space-between;padding:0 max(28px,calc((100vw - 1240px)/2));border-bottom:1px solid rgba(255,255,255,.08);background:rgba(5,11,19,.82);backdrop-filter:blur(18px);position:sticky;top:0;z-index:20}.admin-nav-actions{display:flex;align-items:center;gap:10px}.admin-nav-actions a,.admin-nav-actions button{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#d8e0ea;border-radius:10px;padding:9px 12px;font:inherit;font-size:12px;text-decoration:none;display:flex;align-items:center;gap:7px}.admin-shell{width:min(1240px,calc(100% - 48px));margin:0 auto;padding:60px 0 100px}.admin-header{display:flex;justify-content:space-between;gap:50px;align-items:flex-end;margin-bottom:30px}.admin-header>div{max-width:760px}.admin-header h1{font-size:clamp(42px,6vw,72px);letter-spacing:-.055em;margin:12px 0}.admin-header p{color:#94a1b2;line-height:1.7;margin:0}.admin-clean-button{border:0;border-radius:13px;padding:13px 17px;background:linear-gradient(135deg,#ff9d4d,#ff7f32);color:#101010;font-weight:800;display:flex;gap:8px;align-items:center;white-space:nowrap}.admin-notice{border:1px solid rgba(255,185,104,.25);background:rgba(255,157,77,.08);color:#ffd0a9;padding:13px 15px;border-radius:12px;margin:20px 0}.admin-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:28px 0}.admin-stats>div{padding:20px;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(255,255,255,.035)}.admin-stats span{display:block;color:#7f8da0;text-transform:uppercase;letter-spacing:.09em;font-size:10px}.admin-stats strong{display:block;font-size:28px;margin-top:8px}.admin-panel{margin-top:20px;border:1px solid rgba(255,255,255,.09);border-radius:24px;padding:25px;background:rgba(4,10,18,.48)}.admin-panel-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.admin-panel-heading span{font-size:10px;text-transform:uppercase;letter-spacing:.11em;color:#7acfff}.admin-panel-heading h2{margin:5px 0 0;font-size:25px}.admin-panel-help{color:#7f8da0;font-size:13px;line-height:1.6;margin:10px 0 22px}.admin-refresh{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#dce4ee;padding:9px 12px;border-radius:10px;display:flex;align-items:center;gap:7px}.admin-submission-list{display:grid;gap:14px}.admin-submission-card{display:grid;grid-template-columns:180px 1fr;border:1px solid rgba(255,255,255,.08);border-radius:18px;overflow:hidden;background:rgba(255,255,255,.028)}.admin-submission-card--compact{grid-template-columns:120px 1fr}.admin-submission-image{min-height:190px;background:rgba(255,255,255,.035);display:grid;place-items:center;color:#617084}.admin-submission-card--compact .admin-submission-image{min-height:145px}.admin-submission-image img{width:100%;height:100%;object-fit:cover}.admin-submission-content{padding:18px}.admin-submission-heading{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}.admin-submission-heading div{display:grid;gap:4px}.admin-submission-heading span{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:#718095}.admin-submission-heading strong{font-size:18px}.admin-status{padding:6px 9px;border-radius:999px;background:rgba(255,255,255,.06);font-size:9px!important}.admin-status--approved{color:#8ee5b1;background:rgba(70,190,117,.1)}.admin-status--rejected{color:#ff9f9f;background:rgba(255,90,90,.1)}.admin-edit-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.admin-edit-grid__wide{grid-column:1/-1}.admin-card-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.admin-action{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#dce5ef;padding:8px 10px;border-radius:9px;display:flex;align-items:center;gap:6px;font-size:12px}.admin-action--approve{color:#9ce6b8;border-color:rgba(78,205,128,.22);background:rgba(78,205,128,.08)}.admin-action--reject,.admin-action--danger{color:#ffaaaa;border-color:rgba(255,95,95,.2);background:rgba(255,95,95,.07)}.admin-action:disabled{opacity:.45}.admin-inline-message{margin-top:10px}.admin-empty{padding:24px;border:1px dashed rgba(255,255,255,.09);border-radius:14px;color:#778698;text-align:center}.admin-search{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:10px 10px 10px 14px;border:1px solid rgba(255,255,255,.09);border-radius:15px;background:rgba(255,255,255,.03)}.admin-search>svg{color:#718399}.admin-search input{border:0;background:transparent;padding:8px}.admin-search input:focus{box-shadow:none}.admin-search button{border:0;border-radius:10px;background:#e8f4ff;color:#0a1723;font-weight:800;padding:10px 15px}.admin-search-results{display:grid;gap:8px;margin-top:12px}.admin-search-row{display:grid;grid-template-columns:1.2fr 1.2fr .7fr 1.4fr;gap:12px;padding:13px 15px;border:1px solid rgba(255,255,255,.07);border-radius:13px;background:rgba(255,255,255,.025)}.admin-search-row div{display:grid;gap:4px;min-width:0}.admin-search-row span{color:#6f7e91;text-transform:uppercase;letter-spacing:.08em;font-size:9px}.admin-search-row strong{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n@media(max-width:900px){.admin-header{align-items:flex-start;flex-direction:column}.admin-stats{grid-template-columns:1fr}.admin-submission-card,.admin-submission-card--compact{grid-template-columns:1fr}.admin-submission-image,.admin-submission-card--compact .admin-submission-image{height:220px}.admin-edit-grid{grid-template-columns:1fr 1fr}.admin-search-row{grid-template-columns:1fr 1fr}}\n@media(max-width:600px){.admin-shell{width:min(100% - 24px,1240px);padding-top:32px}.admin-nav{padding:0 12px}.admin-nav-actions a{display:none}.admin-panel{padding:16px}.admin-edit-grid,.admin-search-row{grid-template-columns:1fr}.admin-search{grid-template-columns:auto 1fr}.admin-search button{grid-column:1/-1}.admin-clean-button{width:100%;justify-content:center}.admin-login-card{padding:26px}}\n\n\n/* COMMUNITY LANDMARK SUBMISSION\n\nThe form writes user suggestions into the user_submissions table.\nOnly the landmark name, image URL and country are required. */\n.submission-section{\n  display:grid;\n  grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);\n  gap:34px;\n  margin-top:88px;\n  padding:34px;\n  border:1px solid rgba(255,255,255,.08);\n  border-radius:30px;\n  background:rgba(5,9,14,.54);\n  box-shadow:0 35px 110px rgba(0,0,0,.22);\n  backdrop-filter:blur(22px);\n}\n\n.submission-copy{\n  display:flex;\n  flex-direction:column;\n}\n\n.submission-copy h2{\n  max-width:520px;\n  margin:12px 0 12px;\n  color:#fff;\n  font-size:clamp(34px,4vw,54px);\n  line-height:1;\n}\n\n.submission-copy>p{\n  max-width:520px;\n  margin:0;\n  color:#9aa6b4;\n  line-height:1.65;\n}\n\n.submission-preview{\n  min-height:245px;\n  margin-top:26px;\n  padding:18px;\n  border:1px solid rgba(255,255,255,.08);\n  border-radius:22px;\n  background-size:cover;\n  background-position:center;\n  display:flex;\n  align-items:flex-end;\n  color:#fff;\n  font-size:11px;\n  font-weight:800;\n  letter-spacing:.08em;\n  text-transform:uppercase;\n}\n\n.submission-preview--empty{\n  align-items:center;\n  justify-content:center;\n  flex-direction:column;\n  gap:10px;\n  background:rgba(255,255,255,.025);\n  color:#7f8b99;\n}\n\n.submission-form{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:16px;\n  padding:24px;\n  border:1px solid rgba(255,255,255,.07);\n  border-radius:24px;\n  background:rgba(255,255,255,.025);\n}\n\n.submission-field{\n  display:flex;\n  flex-direction:column;\n  gap:8px;\n}\n\n.submission-field--wide{\n  grid-column:1 / -1;\n}\n\n.submission-field label{\n  color:#cdd6df;\n  font-size:11px;\n  font-weight:750;\n}\n\n.submission-field label span{\n  color:#697582;\n  font-weight:600;\n}\n\n.submission-field input{\n  width:100%;\n  height:46px;\n  padding:0 13px;\n  border:1px solid rgba(255,255,255,.09);\n  border-radius:13px;\n  outline:none;\n  background:rgba(2,5,9,.52);\n  color:#f5f8fb;\n  font:inherit;\n  transition:border-color .2s ease, background .2s ease;\n}\n\n.submission-field input::placeholder{\n  color:#596572;\n}\n\n.submission-field input:focus{\n  border-color:rgba(119,209,167,.42);\n  background:rgba(4,10,14,.74);\n}\n\n.submission-form__footer{\n  grid-column:1 / -1;\n  display:flex;\n  align-items:center;\n  justify-content:space-between;\n  gap:18px;\n  margin-top:4px;\n}\n\n.submission-status{\n  color:#90a0af;\n  font-size:12px;\n  line-height:1.4;\n}\n\n.submission-form button:disabled{\n  opacity:.58;\n  cursor:wait;\n}\n\n@media(max-width:900px){\n  .destination-profile__grid--simple{\n    grid-template-columns:repeat(2,minmax(0,1fr));\n  }\n\n  .submission-section{\n    grid-template-columns:1fr;\n  }\n}\n\n@media(max-width:620px){\n  .destination-profile__grid--simple{\n    grid-template-columns:1fr;\n  }\n\n  .submission-section{\n    padding:20px;\n  }\n\n  .submission-form{\n    grid-template-columns:1fr;\n    padding:18px;\n  }\n\n  .submission-field--wide,\n  .submission-form__footer{\n    grid-column:1;\n  }\n\n  .submission-form__footer{\n    align-items:stretch;\n    flex-direction:column;\n  }\n}\n\n\n/* LANDMARK SUBMISSION RESULT\n\nAfter the backend confirms whether the submission was accepted, the whole\ntile changes into a short result state instead of leaving a small status\nmessage beneath the form. */\n.submission-section--success,\n.submission-section--error{\n  display:block;\n  min-height:430px;\n  position:relative;\n  overflow:hidden;\n}\n\n.submission-section--success{\n  border-color:rgba(119,209,167,.2);\n  background:\n    radial-gradient(circle at 50% 35%, rgba(119,209,167,.10), transparent 34%),\n    rgba(5,9,14,.58);\n}\n\n.submission-section--error{\n  border-color:rgba(225,122,122,.18);\n  background:\n    radial-gradient(circle at 50% 35%, rgba(225,122,122,.08), transparent 34%),\n    rgba(5,9,14,.58);\n}\n\n.submission-result{\n  min-height:360px;\n  display:flex;\n  flex-direction:column;\n  align-items:center;\n  justify-content:center;\n  text-align:center;\n  padding:36px 24px;\n}\n\n.submission-result__icon{\n  width:76px;\n  height:76px;\n  display:grid;\n  place-items:center;\n  margin-bottom:24px;\n  border-radius:24px;\n  backdrop-filter:blur(18px);\n}\n\n.submission-result__icon--success{\n  border:1px solid rgba(119,209,167,.28);\n  background:rgba(119,209,167,.10);\n  color:#8fe0ba;\n  box-shadow:0 0 45px rgba(119,209,167,.10);\n}\n\n.submission-result__icon--error{\n  border:1px solid rgba(225,122,122,.25);\n  background:rgba(225,122,122,.09);\n  color:#e69b9b;\n  box-shadow:0 0 45px rgba(225,122,122,.08);\n}\n\n.submission-result__copy{\n  max-width:680px;\n}\n\n.submission-result__copy h2{\n  margin:12px 0 12px;\n  color:#fff;\n  font-size:clamp(34px,4vw,52px);\n  line-height:1.02;\n}\n\n.submission-result__copy p{\n  max-width:620px;\n  margin:0 auto;\n  color:#9ba7b5;\n  font-size:14px;\n  line-height:1.7;\n}\n\n.submission-result__button{\n  margin-top:28px;\n}\n\n@media(max-width:620px){\n  .submission-section--success,\n  .submission-section--error{\n    min-height:360px;\n  }\n\n  .submission-result{\n    min-height:310px;\n    padding:28px 14px;\n  }\n\n  .submission-result__icon{\n    width:64px;\n    height:64px;\n    border-radius:20px;\n  }\n}\n\n.nav-login[href] { text-decoration:none; display:inline-flex; align-items:center; }\n";

function StyledAdminPage() {
  return <><style>{ADMIN_STYLES}</style><AdminPage /></>;
}

export default StyledAdminPage;
