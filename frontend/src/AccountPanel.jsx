/* User accounts and private saved trips. Admin authentication stays separate. */
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bookmark, Check, LogOut, MapPin, Trash2, UserRound, X, ArrowRight } from 'lucide-react';
const ACCOUNT_STYLES = `
.account-mode-switch{display:flex;gap:5px;padding:5px;margin:0 0 22px;border:1px solid #ffffff21;border-radius:13px;background:#0b1423}
.account-mode-switch button{flex:1;padding:10px 14px;border:0;border-radius:9px;background:transparent;color:#9bb0c8;font:inherit;font-size:13px;cursor:pointer;transition:background .18s,color .18s}
.account-mode-switch button[aria-pressed="true"]{background:#30455c;color:#f0f7ff;box-shadow:0 3px 12px #0003}.account-mode-switch button:disabled{opacity:.6;cursor:wait}
.account-session-actions{display:flex;justify-content:space-between;gap:15px;border-top:1px solid #ffffff15;margin-top:20px}.account-session-actions .account-text-button{margin:14px 0 0}
.account-access{min-height:85vh;display:grid;place-items:center;padding:30px;color:#e1ebfa}.account-access>div{text-align:center;max-width:420px}.account-access h1{font-size:34px;margin:12px 0}.account-access p{color:#b6c7dc;line-height:1.7}.account-access a{display:block;margin-top:24px;color:#a8d4f4;font-size:14px}

.account-nav{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:0;background:transparent;color:inherit;font:inherit;font-size:13px;cursor:pointer;padding:8px 4px;white-space:nowrap}
.account-nav:disabled{opacity:.55;cursor:wait}.account-nav--user span{max-width:110px;overflow:hidden;text-overflow:ellipsis}
.account-overlay{position:fixed;inset:0;z-index:10000;background:rgba(3,8,17,.78);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:20px;animation:account-fade .2s ease}
.account-dialog{position:relative;width:min(100%,590px);max-height:90dvh;overflow-y:auto;overscroll-behavior:contain;padding:34px;border:1px solid #3b465d;border-radius:26px;background:linear-gradient(145deg,#20283b,#101722);color:#f5f7fc;box-shadow:0 32px 100px #0008;animation:account-rise .25s ease}
.account-dialog *{box-sizing:border-box}.account-dialog h2{font-size:30px;line-height:1.2;margin:12px 32px 12px 0}.account-intro{color:#becada;font-size:14px;line-height:1.6;margin:0 0 24px}.account-eyebrow{color:#a6d8f5;font-size:10px;letter-spacing:.15em;font-weight:700;text-transform:uppercase}
.account-close{position:absolute;right:18px;top:18px;background:#ffffff09;color:#cdd9e9;border:1px solid #ffffff22;border-radius:50%;width:34px;height:34px;display:grid;place-items:center;cursor:pointer}
.account-form{display:grid;gap:17px}.account-form label{display:grid;gap:8px;font-size:13px;color:#d5dfed}.account-form input{width:100%;border-radius:12px;padding:13px 14px;border:1px solid #48536b;background:#0f1725;color:#fff;font:inherit;font-size:16px}.account-form small,.account-footnote{color:#aabbd1;font-size:12px;line-height:1.6}
.account-primary{display:inline-flex;justify-content:center;align-items:center;gap:9px;border:1px solid #f5cba1;background:#f2c69b;color:#172233;border-radius:13px;padding:12px 18px;font:inherit;font-size:14px;font-weight:700;cursor:pointer;transition:transform .18s ease,background .18s ease}.account-primary:hover{transform:translateY(-2px);background:#ffdab3}.account-primary:disabled{opacity:.6;cursor:wait;transform:none}.account-primary--saved{background:#1c3d3d;color:#bcf2dc;border-color:#47746b}.account-primary--saved:hover{background:#28504a}
.account-text-button{display:flex;align-items:center;justify-content:center;gap:7px;margin:22px auto 0;background:none;border:0;color:#acd8f3;font:inherit;font-size:13px;cursor:pointer;padding:6px}.account-error{padding:12px 14px;border-radius:10px;background:#852f352c;color:#ffd3d7!important;border:1px solid #b5646a;font-size:13px;line-height:1.6}
.account-trip-list{display:grid;gap:12px}.account-trip{display:flex;gap:14px;align-items:center;padding:13px;background:#ffffff05;border:1px solid #ffffff1c;border-radius:17px}.account-trip>img{width:76px;height:86px;object-fit:cover;border-radius:11px}.account-trip>div{flex:1;min-width:0}.account-trip h3{margin:0 0 8px;font-size:16px;overflow-wrap:anywhere}.account-trip p{display:flex;align-items:center;gap:5px;margin:0 0 10px;color:#b2c0d3;font-size:12px}.account-open{display:inline-flex;align-items:center;gap:5px;background:none;border:0;color:#b1dcf8;padding:0;font:inherit;font-size:12px;cursor:pointer}.account-delete{background:none;color:#c3b0bc;border:0;cursor:pointer;padding:9px}.account-empty{text-align:center;padding:25px 12px;color:#b9cde0}.account-empty>svg{color:#a3d9f7}.account-empty h3{font-size:19px;color:#f1f7ff}.account-empty p{font-size:14px}.account-toast{position:fixed;z-index:11000;bottom:28px;left:50%;transform:translateX(-50%);max-width:calc(100% - 30px);width:max-content;display:flex;gap:10px;align-items:center;background:#1c3c39;border:1px solid #5b9588;color:#e3fff5;padding:14px 20px;border-radius:14px;box-shadow:0 8px 40px #0008;font-size:14px;animation:account-fade .2s ease}
.save-itinerary{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:20px 24px;margin:0 0 25px;border:1px solid #a6d8f52e;border-radius:19px;background:linear-gradient(100deg,#7bbce813,#edba9610)}.save-itinerary>div{flex:1}.save-itinerary p{color:#d1dcea;font-size:14px;margin:7px 0 0}.save-itinerary>small{color:#b1bfd0;font-size:12px}
.account-nav:focus-visible,.account-dialog button:focus-visible,.account-primary:focus-visible,.account-form input:focus-visible{outline:2px solid #b5e1ff;outline-offset:4px}
@keyframes account-fade{from{opacity:0}to{opacity:1}}@keyframes account-rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:700px){.account-dialog{padding:25px 20px}.account-dialog h2{font-size:26px}.save-itinerary{padding:18px;gap:12px}.save-itinerary>div{flex-basis:100%}.nav-links{gap:8px!important}.account-nav{font-size:12px;gap:4px}.account-nav--user span{max-width:70px}.nav-links>a[href='#how']{display:none}.nav-links .upload-mini{font-size:12px;padding:8px}.nav-links .nav-login{font-size:12px}}
@media(prefers-reduced-motion:reduce){.account-overlay,.account-dialog,.account-toast{animation:none}.account-primary{transition:none}}

.trip-plan-editor{margin:0 0 28px;border:1px solid #ffffff20;border-radius:17px;background:#ffffff04;color:#d5e1ef;overflow:hidden}.trip-plan-editor summary{padding:18px 22px;cursor:pointer;font-size:15px}.trip-plan-editor summary>span{font-weight:600;margin-right:16px}.trip-plan-editor summary small{font-size:12px;color:#b4c6dc}.trip-plan-days{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:0 22px 14px}.trip-plan-days label{display:grid;gap:10px;font-size:12px;color:#a8d4f0}.trip-plan-days strong{color:#e0e9f4;margin-left:8px;font-weight:500}.trip-plan-days textarea{width:100%;min-height:95px;border:1px solid #46536a;border-radius:10px;background:#142033;color:#e1ebf8;resize:vertical;padding:12px;line-height:1.6;font:inherit;font-size:14px}.trip-plan-editor>p{padding:0 22px 17px;margin:0;font-size:12px;color:#b6c7db}
@media(max-width:700px){.trip-plan-days{grid-template-columns:1fr}.trip-plan-editor summary small{display:block;margin:7px 0 0 17px}.nav-inner{gap:10px}.nav-links .upload-mini{font-size:0!important;padding:8px!important}.account-nav--user{border:1px solid #ffffff22;border-radius:50%;width:34px;height:34px}.account-nav--user span{display:none}.account-nav--user svg{width:17px}.account-nav--user::after{content:none}}

`;


export function apiErrorMessage(data, fallback = 'The request could not be completed.') {
  if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail;
  if (Array.isArray(data?.detail)) {
    const labels = { image: 'Landmark photo', file: 'Image file', name: 'Landmark name', country: 'Country', lat: 'Latitude', lon: 'Longitude' };
    const messages = data.detail.map(item => {
      if (typeof item === 'string') return item;
      const key = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : '';
      return typeof item?.msg === 'string' ? `${labels[key] || key || 'Field'}: ${item.msg}` : '';
    }).filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  return typeof data?.message === 'string' ? data.message : fallback;
}

const AccountContext = createContext(null);

function defaultPlan(destination) {
  return [
    { day: 'Day 1', title: 'Arrive + settle in', notes: 'Check in and explore the neighborhood.' },
    { day: 'Day 2', title: 'The main event', notes: `Visit ${destination.name}, then leave time for a local meal.` },
    { day: 'Day 3', title: 'One more discovery', notes: 'Explore a nearby spot before heading home.' },
  ];
}

export function ItineraryPlan({ destination, onChange }) {
  const plan = destination.itinerary || defaultPlan(destination);
  return <details className="trip-plan-editor">
    <summary><span>Your trip plan</span><small>Make it yours · edit day by day</small></summary>
    <div className="trip-plan-days">{plan.map((day, index) => <label key={index}>
      <span>{day.day} <strong>{day.title}</strong></span>
      <textarea aria-label={`${day.day} itinerary`} rows={2} maxLength={1500} value={day.notes || ''}
        onChange={event => onChange(plan.map((item, i) => i === index ? { ...item, notes: event.target.value } : item))}/>
    </label>)}</div>
    <p>Your edits are included when you save this itinerary.</p>
  </details>;
}

export function AccountProvider({ children, apiBaseUrl, navigateToAdmin = () => window.location.assign('/admin') }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [trips, setTrips] = useState([]);
  const [panel, setPanel] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [authMode, setAuthMode] = useState('traveler');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [pendingName, setPendingName] = useState('');
  const pending = useRef(null);
  const onOpen = useRef(null);
  const dialog = useRef(null);
  const trigger = useRef(null);
  const authGeneration = useRef(0);
  const actionLock = useRef(false);

  async function api(path, options = {}) {
    const response = await fetch(`${apiBaseUrl}${path}`, { ...options, credentials: 'include',
      headers: { 'X-Trekmark-Request': '1', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(apiErrorMessage(data, 'Please check your details and try again.'));
      error.status = response.status;
      throw error;
    }
    return data;
  }
  async function refreshTrips() {
    const generation = authGeneration.current;
    const data = await api('/api/favorites');
    if (generation === authGeneration.current) setTrips(data.favorites || []);
  }
  useEffect(() => {
    let active = true;
    api('/api/auth/me').then(async data => {
      if (!active) return;
      setUser(data.user);
      try { await refreshTrips(); } catch { /* The panel can retry loading later. */ }
    }).catch(() => {}).finally(() => { if (active) setChecking(false); });
    return () => { active = false; authGeneration.current += 1; };
  }, [apiBaseUrl]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!panel) return;
    trigger.current = document.activeElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.querySelector('input, button')?.focus();
    const key = event => {
      if (event.key === 'Escape' && !actionLock.current) close();
      if (event.key === 'Tab') {
        const nodes = [...(dialog.current?.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href]') || [])];
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.body.style.overflow = previous; document.removeEventListener('keydown', key); trigger.current?.focus?.(); };
  }, [panel]);

  function close() {
    if (actionLock.current) return;
    setPanel(null); setMessage(''); pending.current = null; setPendingName('');
  }
  function openLogin(mode = 'traveler') {
    setAuthMode(mode);
    pending.current = null; setPendingName(''); setRegistering(false); setMessage(''); setPanel('auth');
  }
  function snapshot(destination) {
    // Nearby recommendations refresh on return. Keep the destination/itinerary,
    // not temporary upload previews or stale provider response objects.
    const { hotelSearch, restaurantSearch, ...saved } = destination;
    saved.itinerary = destination.itinerary || defaultPlan(destination);
    for (const key of ['hero', 'stayImage', 'eatImage', 'experienceImage']) {
      if (typeof saved[key] === 'string' && saved[key].startsWith('blob:')) delete saved[key];
    }
    return JSON.parse(JSON.stringify(saved));
  }
  async function persist(destination) {
    await api('/api/favorites', { method: 'POST', body: JSON.stringify({
      title: destination.name.slice(0, 120), destination: snapshot(destination) }) });
    await refreshTrips();
    setNotice('Trip saved. Find it in Saved trips.');
  }
  async function saveTrip(destination) {
    if (!destination || actionLock.current) return;
    pending.current = destination;
    setPendingName(destination.name);
    if (!user) { setAuthMode('traveler'); setRegistering(false); setMessage(''); setPanel('auth'); return; }
    actionLock.current = true; setBusy(true);
    try { await persist(destination); pending.current = null; setPendingName(''); }
    catch (error) {
      if (error.status === 401) { authGeneration.current += 1; setUser(null); setTrips([]); setAuthMode('traveler'); setPanel('auth'); }
      else setNotice(error.message || 'Could not save this trip.');
    } finally { actionLock.current = false; setBusy(false); }
  }
  async function authenticate(event) {
    event.preventDefault();
    if (actionLock.current) return;
    const form = new FormData(event.currentTarget);
    const admin = authMode === 'admin';
    const body = admin ? { username: form.get('username'), password: form.get('password') } : { email: form.get('email'), password: form.get('password') };
    if (!admin && registering) body.display_name = form.get('display_name');
    actionLock.current = true; setBusy(true); setMessage('');
    try {
      if (admin) {
        const data = await api('/admin/login', { method: 'POST', body: JSON.stringify(body) });
        if (typeof data.access_token !== 'string' || !data.access_token) throw new Error('Admin sign-in did not return a session.');
        localStorage.setItem('trekmark_admin_token', data.access_token);
        pending.current = null; setPendingName(''); setPanel(null);
        navigateToAdmin();
        return;
      }
      const data = await api(`/api/auth/${registering ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify(body) });
      authGeneration.current += 1; setUser(data.user); setTrips([]);
      if (pending.current) await persist(pending.current);
      else await refreshTrips();
      pending.current = null; setPendingName('');
      if (window.location.pathname === '/admin' || window.location.pathname.startsWith('/admin/')) {
        setPanel(null); window.location.assign('/');
      } else setPanel('saved');
    } catch (error) { setMessage(error.message || 'Cannot reach the backend. Check that it is running.'); }
    finally { actionLock.current = false; setBusy(false); }
  }
  async function openSaved(callback) {
    onOpen.current = callback;
    if (!user) { openLogin(); return; }
    setMessage(''); setPanel('saved'); setBusy(true);
    try { await refreshTrips(); }
    catch (error) {
      setMessage(error.message);
      if (error.status === 401) { authGeneration.current += 1; setUser(null); setTrips([]); setAuthMode('traveler'); setPanel('auth'); }
    } finally { setBusy(false); }
  }
  async function logout() {
    if (actionLock.current) return;
    actionLock.current = true; setBusy(true);
    try {
      await api('/api/auth/logout', { method: 'POST' });
      authGeneration.current += 1; setUser(null); setTrips([]); setPanel(null); pending.current = null; setPendingName(''); setNotice('Signed out. Your saved trips are still in your account.');
    } catch (error) { setMessage(error.message); }
    finally { actionLock.current = false; setBusy(false); }
  }
  async function remove(id) {
    if (actionLock.current) return;
    actionLock.current = true; setBusy(true); setMessage('');
    try { await api(`/api/favorites/${id}`, { method: 'DELETE' }); setTrips(current => current.filter(trip => trip.id !== id)); }
    catch (error) { setMessage(error.message); }
    finally { actionLock.current = false; setBusy(false); }
  }
  const setOpenHandler = callback => { onOpen.current = callback; };
  const context = { user, checking, busy, trips, openLogin, openSaved, saveTrip, setOpenHandler };
  return <AccountContext.Provider value={context}><style>{ACCOUNT_STYLES}</style>{children}
    {notice && createPortal(<div className="account-toast" role="status"><Check size={18}/>{notice}</div>, document.body)}
    {panel && createPortal(<div className="account-overlay" onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <section className="account-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="account-title">
        <button className="account-close" onClick={close} disabled={busy} aria-label="Close account panel"><X size={21}/></button>
        <span className="account-eyebrow">{authMode === 'admin' && panel === 'auth' ? 'Trekmark workspace' : 'Your next escape'}</span>
        <h2 id="account-title">{panel === 'auth' ? authMode === 'admin' ? 'Admin sign in' : registering ? 'Make room for more trips.' : 'Welcome back.' : 'Saved trips'}</h2>
        <p className="account-intro">{panel === 'auth' ? authMode === 'admin' ? 'Review landmarks. Keep discoveries moving.' : pendingName ? `Sign in to save your ${pendingName} itinerary.` : 'Build it. Save it. Come back anytime.' : `${user?.display_name || 'Your'}’s collection. Open a trip whenever you’re ready.`}</p>
        {panel === 'auth' ? <>
          <div className="account-mode-switch" role="group" aria-label="Sign-in type">
            <button type="button" aria-pressed={authMode === 'traveler'} disabled={busy} onClick={() => { setAuthMode('traveler'); setRegistering(false); setMessage(''); }}>Traveler</button>
            <button type="button" aria-pressed={authMode === 'admin'} disabled={busy} onClick={() => { setAuthMode('admin'); setRegistering(false); setMessage(''); }}>Admin</button>
          </div>
          <form key={`${authMode}-${registering}`} onSubmit={authenticate} className="account-form">
            {authMode === 'traveler' && registering && <label>Your name<input name="display_name" autoComplete="name" maxLength={80} required disabled={busy}/></label>}
            {authMode === 'admin'
              ? <label>Admin username<input name="username" autoComplete="username" maxLength={100} required disabled={busy}/></label>
              : <label>Email<input type="email" name="email" autoComplete="email" maxLength={254} required disabled={busy}/></label>}
            <label>Password<input type="password" name="password" autoComplete={authMode === 'traveler' && registering ? 'new-password' : 'current-password'} minLength={authMode === 'traveler' && registering ? 10 : 1} maxLength={128} required disabled={busy}/></label>
            {authMode === 'traveler' && registering && <small>Use at least 10 characters.</small>}
            {message && <p className="account-error" role="alert">{message}</p>}
            <button className="account-primary" disabled={busy}>{busy ? 'One moment…' : authMode === 'admin' ? 'Open admin workspace' : registering ? 'Create account' : 'Sign in'} <ArrowRight size={17}/></button>
          </form>
          {authMode === 'traveler' && <button className="account-text-button" disabled={busy} onClick={() => { setRegistering(value => !value); setMessage(''); }}>{registering ? 'Already have an account? Sign in' : 'New here? Create an account'}</button>}
        </> : <>
          {message && <p className="account-error" role="alert">{message}</p>}
          {busy && <p role="status">Updating your collection…</p>}
          {!busy && trips.length === 0 && <div className="account-empty"><Bookmark size={30}/><h3>Your next trip starts with a photo.</h3><p>Build a trip, then tap Save itinerary.</p><button className="account-primary" onClick={close}>Explore destinations <ArrowRight size={16}/></button></div>}
          <div className="account-trip-list">{trips.map(trip => <article className="account-trip" key={trip.id}>
            {trip.destination.hero && /^https?:\/\//.test(trip.destination.hero) && <img src={trip.destination.hero} alt="" loading="lazy" onError={event => { event.currentTarget.style.display = 'none'; }}/>}
            <div><h3>{trip.title}</h3><p><MapPin size={13}/>{trip.destination.country || trip.destination.countryName || 'Saved destination'}</p>
              <button disabled={busy} className="account-open" onClick={() => { onOpen.current?.({ ...trip.destination, hotelSearch: null, restaurantSearch: null }); close(); }}>Open itinerary <ArrowRight size={14}/></button>
            </div><button className="account-delete" disabled={busy} aria-label={`Remove ${trip.title} from saved trips`} onClick={() => remove(trip.id)}><Trash2 size={17}/></button>
          </article>)}</div>
          {trips.length > 0 && <p className="account-footnote">Your itinerary stays saved. Nearby options refresh when you open it.</p>}
          <div className="account-session-actions"><button className="account-text-button" disabled={busy} onClick={() => openLogin('admin')}>Admin access</button>
          <button className="account-text-button" disabled={busy} onClick={logout}><LogOut size={15}/> Sign out</button></div>
        </>}
      </section>
    </div>, document.body)}
  </AccountContext.Provider>;
}

export function AccountNav({ onOpenTrip }) {
  const { user, checking, busy, openLogin, openSaved, setOpenHandler } = useContext(AccountContext);
  useEffect(() => setOpenHandler(onOpenTrip), [onOpenTrip]);
  return <><button className="account-nav" disabled={checking || busy} onClick={() => openSaved(onOpenTrip)}><Bookmark size={15}/><span>Saved trips</span></button>
    <button className="account-nav account-nav--user" aria-label={user ? `Account for ${user.display_name}` : 'Sign in'} title={user ? user.display_name : 'Sign in'} disabled={checking || busy} onClick={() => user ? openSaved(onOpenTrip) : openLogin()}><UserRound size={15}/><span>{checking ? '…' : user ? user.display_name : 'Sign in'}</span></button></>;
}

export function SaveItinerary({ destination }) {
  const { user, checking, busy, trips, saveTrip } = useContext(AccountContext);
  const exists = trips.some(trip => String(trip.destination.id) === String(destination.id));
  return <div className="save-itinerary">
    <div><span className="account-eyebrow">Discover. Plan. Keep.</span><p>{exists ? 'A little closer to your next adventure.' : 'Love this plan? Keep it for later.'}</p></div>
    <button className={exists ? 'account-primary account-primary--saved' : 'account-primary'} disabled={checking || busy} onClick={() => saveTrip(destination)}>
      {exists ? <Check size={17}/> : <Bookmark size={17}/>} {busy ? 'Saving…' : exists ? 'Saved · update itinerary' : 'Save itinerary'}
    </button>
    {!user && <small>Sign in when you save.</small>}
  </div>;
}


export function AdminAccess() {
  const { openLogin } = useContext(AccountContext);
  useEffect(() => { openLogin('admin'); }, []);
  return <main className="account-access"><div><span className="account-eyebrow">Trekmark workspace</span>
    <h1>Every great discovery starts here.</h1><p>Sign in to review community landmarks.</p>
    <button className="account-primary" onClick={() => openLogin('admin')}>Sign in <ArrowRight size={16}/></button>
    <a href="/">Back to exploring</a>
  </div></main>;
}
