(() => {
  'use strict';

  const DB_NAME = 'aurix-admin-local';
  const DB_VERSION = 1;
  const AUTH_KEY = 'aurix-admin-auth-v1';
  const SESSION_KEY = 'aurix-admin-session-v1';
  const SESSION_MS = 30 * 60 * 1000;
  const STATE_KEYS = ['users', 'releases', 'files', 'announcements', 'activities', 'logins', 'website', 'products', 'orders', 'customers', 'categories', 'coupons', 'store'];
  const DEFAULTS = {
    users: [], releases: [], files: [], announcements: [], activities: [], logins: [],
    products: [], orders: [], customers: [], categories: [], coupons: [],
    store: {name:'AURIX', currency:'USD', shippingInfo:'Standard shipping: 3-5 business days.', paymentStatuses:['Pending','Paid','Refunded']},
    website: {
      title: 'AURIX', tagline: 'Your World, Connected.', hero: 'A private workspace for notes, projects, files, and ideas.',
      announcement: '', about: 'AURIX keeps your work organized on your own computer.',
      software: 'A local-first desktop workspace for Windows.', comingSoon: '', downloadNote: 'Free for personal use. Works offline.',
      contactEmail: '', footer: 'Built with care. Your data stays yours.'
    }
  };
  const $ = (selector, root = document) => root.querySelector(selector);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const uid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const dateText = value => value ? new Date(value).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}) : 'Never';
  const dayKey = value => new Date(value).toISOString().slice(0, 10);
  const formatBytes = value => {
    if (!value) return '0 B';
    const units = ['B','KB','MB','GB'];
    const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  };
  const relativeTime = value => {
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  };
  const dbRequest = request => new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Browser storage request failed.'));
  });
  let database;
  let routeName = 'overview';
  let routeSequence = 0;
  let temporaryObjectUrl = null;
  let temporaryObjectUrls = [];
  let commerceHandlers = {};

  function openDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const next = request.result;
        if (!next.objectStoreNames.contains('state')) next.createObjectStore('state', {keyPath:'key'});
        if (!next.objectStoreNames.contains('blobs')) next.createObjectStore('blobs', {keyPath:'id'});
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB could not be opened. Start AURIX with run_admin.py.'));
      request.onblocked = () => reject(new Error('Close other AURIX admin tabs, then reload this page.'));
    });
  }

  async function getState(key) {
    const record = await dbRequest(database.transaction('state', 'readonly').objectStore('state').get(key));
    return record ? record.value : structuredClone(DEFAULTS[key]);
  }

  async function setState(key, value) {
    const tx = database.transaction('state', 'readwrite');
    tx.objectStore('state').put({key, value});
    await new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error('Could not save local data.'));
      tx.onabort = () => reject(tx.error || new Error('Local save was cancelled.'));
    });
  }

  async function setManyState(values) {
    const tx = database.transaction('state', 'readwrite');
    for (const [key, value] of Object.entries(values)) tx.objectStore('state').put({key, value});
    await new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error('Could not save local data.'));
      tx.onabort = () => reject(tx.error || new Error('Local save was cancelled.'));
    });
  }

  async function putBlob(id, file) {
    const tx = database.transaction('blobs', 'readwrite');
    tx.objectStore('blobs').put({id, blob:file, name:file.name, type:file.type || 'application/octet-stream', size:file.size, modified:file.lastModified || Date.now()});
    await new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error('Could not store this file. Browser storage may be full.'));
      tx.onabort = () => reject(tx.error || new Error('File storage was cancelled.'));
    });
  }

  async function getBlob(id) {
    return dbRequest(database.transaction('blobs', 'readonly').objectStore('blobs').get(id));
  }

  async function removeBlob(id) {
    const tx = database.transaction('blobs', 'readwrite');
    tx.objectStore('blobs').delete(id);
    await new Promise((resolve, reject) => {
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error || new Error('Could not remove the stored file.'));
    });
  }

  async function allBlobs() {
    return dbRequest(database.transaction('blobs', 'readonly').objectStore('blobs').getAll());
  }

  function toast(message, kind = 'info') {
    const item = document.createElement('div');
    item.className = `toast toast-${kind}`;
    item.textContent = message;
    $('#toastStack').append(item);
    window.setTimeout(() => item.remove(), 4200);
  }

  function confirmAction(title, message) {
    return new Promise(resolve => {
      const dialog = $('#confirmDialog');
      $('#confirmTitle').textContent = title;
      $('#confirmMessage').textContent = message;
      const done = value => {
        dialog.close();
        $('#confirmYes').removeEventListener('click', yes);
        $('#confirmNo').removeEventListener('click', no);
        dialog.removeEventListener('cancel', cancel);
        resolve(value);
      };
      const yes = () => done(true);
      const no = () => done(false);
      const cancel = event => { event.preventDefault(); done(false); };
      $('#confirmYes').addEventListener('click', yes, {once:true});
      $('#confirmNo').addEventListener('click', no, {once:true});
      dialog.addEventListener('cancel', cancel, {once:true});
      dialog.showModal();
    });
  }

  async function recordActivity(action, detail = '') {
    const list = await getState('activities');
    list.unshift({id:uid(), action, detail, at:new Date().toISOString()});
    await setState('activities', list.slice(0, 500));
  }

  function readAuth() {
    try { return JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); }
    catch { return null; }
  }

  function readSession() {
    try {
      const session = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
      return session && session.expiresAt > Date.now() ? session : null;
    } catch { return null; }
  }

  function saveSession() {
    const auth = readAuth();
    if (!auth) return;
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({email:auth.email, name:auth.name, expiresAt:Date.now() + SESSION_MS}));
  }

  function requireCrypto() {
    if (!window.crypto?.subtle || !window.isSecureContext) {
      throw new Error('Secure browser storage is unavailable. Start the dashboard with run_admin.py instead of opening the HTML directly.');
    }
  }

  function bytesToHex(bytes) {
    return [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  }

  async function passwordHash(password, salt) {
    requireCrypto();
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']);
    const derived = await crypto.subtle.deriveBits({name:'PBKDF2', salt, iterations:210000, hash:'SHA-256'}, material, 256);
    return bytesToHex(derived);
  }

  function hexToBytes(hex) {
    return new Uint8Array(hex.match(/.{1,2}/g).map(pair => parseInt(pair, 16)));
  }

  function showAuth() {
    const auth = readAuth();
    $('#authView').classList.remove('hidden');
    $('#appShell').classList.add('hidden');
    $('#authView').innerHTML = auth ? `
      <section class="auth-panel">
        <div class="brand-mark">A</div><p class="eyebrow">AURIX / LOCAL ADMIN</p>
        <h1>Welcome back<span class="accent">.</span></h1>
        <p class="muted">Sign in to this browser’s local command center.</p>
        <form id="loginForm" class="form-stack">
          <label>Administrator email<input name="email" type="email" autocomplete="username" value="${escapeHtml(auth.email)}" required></label>
          <label>Password<input name="password" type="password" autocomplete="current-password" required autofocus></label>
          <button class="button primary wide" type="submit">Unlock dashboard <span aria-hidden="true">→</span></button>
        </form>
        <div class="local-notice"><span class="status-dot"></span><span>Local prototype · Stored only in this browser</span></div>
        <p class="security-copy">Local-only authentication is for a private prototype, not a secure public production admin system.</p>
      </section>` : `
      <section class="auth-panel">
        <div class="brand-mark">A</div><p class="eyebrow">AURIX / FIRST-RUN SETUP</p>
        <h1>Create your local admin<span class="accent">.</span></h1>
        <p class="muted">This creates a browser-local password hash. No account or network service is used.</p>
        <form id="setupForm" class="form-stack">
          <label>Display name<input name="name" autocomplete="name" maxlength="80" required></label>
          <label>Administrator email<input name="email" type="email" autocomplete="email" maxlength="180" required></label>
          <label>Password<input name="password" type="password" autocomplete="new-password" minlength="10" required><small>Use at least 10 characters.</small></label>
          <label>Confirm password<input name="confirm" type="password" autocomplete="new-password" minlength="10" required></label>
          <button class="button primary wide" type="submit">Create local admin <span aria-hidden="true">→</span></button>
        </form>
        <div class="local-notice"><span class="status-dot"></span><span>First run · No external APIs or cloud services</span></div>
        <p class="security-copy">Local-only authentication is for a private prototype, not a secure public production admin system.</p>
      </section>`;
  }

  async function setupAdmin(form) {
    const data = new FormData(form);
    const name = String(data.get('name') || '').trim();
    const email = String(data.get('email') || '').trim().toLowerCase();
    const password = String(data.get('password') || '');
    const confirm = String(data.get('confirm') || '');
    if (!name || !email) throw new Error('Enter a display name and administrator email.');
    if (password.length < 10) throw new Error('Choose a password with at least 10 characters.');
    if (password !== confirm) throw new Error('The passwords do not match.');
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const hash = await passwordHash(password, salt);
    localStorage.setItem(AUTH_KEY, JSON.stringify({name, email, salt:bytesToHex(salt), hash, createdAt:new Date().toISOString()}));
    saveSession();
    await setManyState(DEFAULTS);
    await recordActivity('Local admin created', email);
    await recordLogin(email);
    launchApp();
  }

  async function recordLogin(email) {
    const history = await getState('logins');
    history.unshift({id:uid(), email, at:new Date().toISOString(), device:navigator.userAgentData?.platform || navigator.platform || 'This browser'});
    await setState('logins', history.slice(0, 100));
  }

  async function loginAdmin(form) {
    const data = new FormData(form);
    const email = String(data.get('email') || '').trim().toLowerCase();
    const password = String(data.get('password') || '');
    const auth = readAuth();
    if (!auth || email !== auth.email) throw new Error('Email or password is incorrect.');
    const hash = await passwordHash(password, hexToBytes(auth.salt));
    if (hash !== auth.hash) throw new Error('Email or password is incorrect.');
    saveSession();
    await recordLogin(email);
    await recordActivity('Admin signed in', email);
    launchApp();
  }

  function launchApp() {
    $('#authView').classList.add('hidden');
    $('#appShell').classList.remove('hidden');
    const session = readSession();
    $('#adminName').textContent = session?.name || 'Administrator';
    $('#adminEmail').textContent = session?.email || '';
    renderRoute();
  }

  function touchSession() {
    if (!readSession()) return;
    saveSession();
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    showAuth();
    toast('You are signed out.');
  }

  function navMarkup() {
    return [
      ['overview','Overview','◫'], ['products','Products','▣'], ['orders','Orders','▤'],
      ['customers','Customers','♙'], ['categories','Categories','▦'], ['coupons','Coupons','％'],
      ['reports','Reports & analytics','⌁'], ['store-settings','Store settings','⚙'], ['users','Users','♙'], ['releases','Software & releases','⬡'],
      ['files','File library','▧'], ['announcements','Announcements','▤'], ['website','Website content','⌘'],
      ['activity','Activity log','◷'], ['settings','Settings & backup','⚙']
    ].map(([key,label,icon]) => `<button class="nav-link" data-route="${key}" type="button"><span class="nav-icon">${icon}</span><span>${label}</span></button>`).join('');
  }

  function setPage(title, subtitle, action = '') {
    $('#pageTitle').textContent = title;
    $('#pageSubtitle').textContent = subtitle;
    $('#pageAction').innerHTML = action;
  }

  function metricCard(label, value, note, icon, tone = '') {
    return `<article class="metric-card ${tone}"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><strong>${value}</strong><small>${note}</small></article>`;
  }

  function emptyState(title, message, action = '') {
    return `<div class="empty-state"><span class="empty-mark">＋</span><h3>${title}</h3><p>${message}</p>${action}</div>`;
  }

  function tableEmpty(columns, message) {
    return `<tr><td class="table-empty" colspan="${columns}">${message}</td></tr>`;
  }

  function activityRows(items, limit = 8) {
    return items.slice(0, limit).map(item => `<div class="activity-row"><span class="activity-mark"></span><div class="activity-copy"><b>${escapeHtml(item.action)}</b><span>${escapeHtml(item.detail || 'Local admin action')}</span></div><time>${relativeTime(item.at)}</time></div>`).join('') || '<p class="muted small">No activity recorded yet.</p>';
  }

  function barsSvg(values, label) {
    const max = Math.max(1, ...values.map(item => item.value));
    const width = 560, height = 176, chartHeight = 120, gap = 12;
    const barWidth = (width - gap * (values.length + 1)) / values.length;
    const bars = values.map((item, index) => {
      const x = gap + index * (barWidth + gap);
      const barHeight = item.value ? Math.max(5, item.value / max * chartHeight) : 2;
      const y = chartHeight - barHeight + 8;
      return `<g><rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="url(#chartPaint)"><title>${escapeHtml(item.label)}: ${item.value} ${label}</title></rect><text x="${x + barWidth / 2}" y="157" text-anchor="middle">${escapeHtml(item.short)}</text></g>`;
    }).join('');
    return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${label} for the last seven days"><defs><linearGradient id="chartPaint" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#69d4ff"/><stop offset="1" stop-color="#9b78ff"/></linearGradient></defs><path class="chart-grid" d="M0 128H560M0 88H560M0 48H560"/>${bars}<text class="chart-unit" x="4" y="17">${escapeHtml(label)}</text></svg>`;
  }

  async function renderOverview() {
    setPage('Overview', 'Your store at a glance.', '<button class="button secondary" data-action="export-backup">Export backup <span aria-hidden="true">↗</span></button>');
    const [users, releases, activities, logins, files, announcements, blobs, products, orders, customers, store] = await Promise.all([
      getState('users'), getState('releases'), getState('activities'), getState('logins'), getState('files'), getState('announcements'), allBlobs(),
      getState('products'), getState('orders'), getState('customers'), getState('store')
    ]);
    const totalDownloads = releases.reduce((sum, release) => sum + (Number(release.downloads) || 0), 0);
    const storedBytes = blobs.reduce((sum, record) => sum + (record.size || record.blob?.size || 0), 0);
    const activeUsers = users.filter(user => user.status === 'active').length;
    const published = releases.filter(release => release.status === 'published').length;
    const revenue = orders.filter(order => order.status !== 'Cancelled').reduce((sum, order) => sum + Number(order.total || 0), 0);
    const orderStates = ['Pending','Processing','Shipped','Delivered','Cancelled'];
    const orderCounts = Object.fromEntries(orderStates.map(status => [status, orders.filter(order => order.status === status).length]));
    const week = Array.from({length:7}, (_, index) => {
      const date = new Date(); date.setDate(date.getDate() - (6 - index));
      const key = dayKey(date);
      return {key, label:date.toLocaleDateString([], {weekday:'long'}), short:date.toLocaleDateString([], {weekday:'short'}), value:orders.filter(order => order.createdAt && dayKey(order.createdAt) === key && order.status !== 'Cancelled').reduce((sum, order) => sum + Number(order.total || 0), 0)};
    });
    const recentLogins = logins.slice(0, 5).map(login => `<tr><td>${dateText(login.at)}</td><td>${escapeHtml(login.email)}</td><td>${escapeHtml(login.device || 'This browser')}</td></tr>`).join('') || tableEmpty(3, 'No sign-ins recorded yet.');
    const announcementsLive = announcements.filter(item => item.status === 'published').length;
    $('#view').innerHTML = `
      <div class="metrics-grid">
        ${metricCard('Total revenue', formatMoney(revenue, store.currency), `${orders.length} recorded orders`, '$')}
        ${metricCard('Total orders', orders.length, `${orderCounts.Pending || 0} pending`, '▤', 'tone-blue')}
        ${metricCard('Total products', products.length, `${products.filter(product => product.enabled).length} active`, '▣', 'tone-cyan')}
        ${metricCard('Total customers', customers.length, `${users.length} AURIX accounts`, '♙', 'tone-violet')}
      </div>
      <div class="dashboard-grid">
        <section class="panel chart-panel"><div class="panel-heading"><div><p class="eyebrow">SALES ANALYTICS</p><h2>Revenue</h2></div><span class="period-label">Last 7 days</span></div>${barsSvg(week, 'Revenue')}<div class="chart-foot"><span>Excludes cancelled orders</span><span>${formatMoney(revenue, store.currency)} lifetime</span></div></section>
        <section class="panel status-panel"><div class="panel-heading"><div><p class="eyebrow">ORDER PIPELINE</p><h2>Order status</h2></div><button class="text-button" data-route="orders">Manage orders →</button></div><div class="status-list">${orderStates.map(status => `<div><span>${status} orders</span><b>${orderCounts[status] || 0}</b></div>`).join('')}</div></section>
        <section class="panel"><div class="panel-heading"><div><p class="eyebrow">LATEST ORDERS</p><h2>Recent orders</h2></div><button class="text-button" data-route="orders">View all →</button></div><div class="table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Total</th><th>Status</th></tr></thead><tbody>${orders.slice().sort((a,b)=>new Date(b.createdAt)-new Date(a.createdAt)).slice(0,6).map(order => `<tr><td>#${escapeHtml(order.number)}</td><td>${escapeHtml(order.customerName)}</td><td>${formatMoney(order.total, store.currency)}</td><td><span class="state-chip ${order.status === 'Delivered' ? 'positive' : order.status === 'Cancelled' ? 'negative' : 'neutral'}">${escapeHtml(order.status)}</span></td></tr>`).join('') || tableEmpty(4,'No orders recorded yet.')}</tbody></table></div></section>
        <section class="panel"><div class="panel-heading"><div><p class="eyebrow">BEST SELLERS</p><h2>Product performance</h2></div><button class="text-button" data-route="products">Products →</button></div><div class="status-list">${topProducts(orders, products, store.currency)}</div></section>
      </div>`;
  }

  function formatMoney(value, currency = 'USD') {
    try { return new Intl.NumberFormat(undefined, {style:'currency', currency}).format(Number(value) || 0); }
    catch { return `${currency} ${(Number(value) || 0).toFixed(2)}`; }
  }

  function topProducts(orders, products, currency) {
    const sold = new Map();
    for (const order of orders) if (order.status !== 'Cancelled') for (const item of order.items || []) {
      const current = sold.get(item.productId) || {name:item.name, quantity:0, revenue:0};
      current.quantity += Number(item.quantity) || 0;
      current.revenue += (Number(item.price) || 0) * (Number(item.quantity) || 0);
      sold.set(item.productId, current);
    }
    return [...sold.values()].sort((a,b)=>b.quantity-a.quantity).slice(0,5).map(item => `<div><span>${escapeHtml(item.name)}</span><b>${item.quantity} sold <em>${formatMoney(item.revenue, currency)}</em></b></div>`).join('') || '<p class="muted small">Sales will appear here when orders are added.</p>';
  }

  async function renderProducts() {
    setPage('Products', 'Manage your catalog, pricing, availability, and stock.', '<button class="button primary" data-action="new-product">＋ Add product</button>');
    const [products, categories, store] = await Promise.all([getState('products'), getState('categories'), getState('store')]);
    const rows = await Promise.all(products.map(async product => {
      let image = '';
      if (product.imageBlobId) { const saved = await getBlob(product.imageBlobId); if (saved?.blob) { const url = URL.createObjectURL(saved.blob); temporaryObjectUrls.push(url); image = `<img class="product-thumb" src="${url}" alt="">`; } }
      const category = categories.find(item => item.id === product.categoryId)?.name || 'Uncategorized';
      return `<tr><td><div class="identity-cell">${image || '<span class="product-thumb product-placeholder">▣</span>'}<div><b>${escapeHtml(product.name)}</b><small>${escapeHtml(category)}${product.featured ? ' · Featured' : ''}</small></div></div></td><td>${formatMoney(product.price, store.currency)}${product.discountPrice ? `<small class="discount-price">${formatMoney(product.discountPrice, store.currency)}</small>` : ''}</td><td>${Number(product.stock) || 0}</td><td><span class="state-chip ${product.enabled ? 'positive' : 'neutral'}">${product.enabled ? 'Enabled' : 'Disabled'}</span></td><td class="actions-cell"><button class="icon-button" title="Edit product" aria-label="Edit product" data-action="edit-product" data-id="${product.id}">✎</button><button class="icon-button danger-icon" title="Delete product" aria-label="Delete product" data-action="delete-product" data-id="${product.id}">×</button></td></tr>`;
    }));
    $('#view').innerHTML = `<section class="panel table-panel"><div class="toolbar"><div class="search-field"><span>⌕</span><input id="productSearch" type="search" placeholder="Search products" aria-label="Search products"></div><select id="productCategoryFilter" class="filter-select"><option value="">All categories</option>${categories.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('')}</select><select id="productStateFilter" class="filter-select"><option value="">All statuses</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option><option value="low">Low stock</option></select><span class="toolbar-count">${products.length} products</span></div><div class="table-wrap"><table><thead><tr><th>Product</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th></tr></thead><tbody id="productRows"></tbody></table></div></section>`;
    const draw = () => {
      const query = $('#productSearch').value.trim().toLowerCase(), category = $('#productCategoryFilter').value, filter = $('#productStateFilter').value;
      const matches = products.map((product,index)=>({product,row:rows[index]})).filter(({product}) => (!category || product.categoryId === category) && (!filter || (filter === 'enabled' ? product.enabled : filter === 'disabled' ? !product.enabled : Number(product.stock) <= 5)) && `${product.name} ${product.description}`.toLowerCase().includes(query));
      $('#productRows').innerHTML = matches.map(item=>item.row).join('') || tableEmpty(5,'No products match these filters.');
    };
    $('#productSearch').addEventListener('input', draw); $('#productCategoryFilter').addEventListener('change', draw); $('#productStateFilter').addEventListener('change', draw); draw();
  }

  async function openProductForm(product = null) {
    const categories = await getState('categories');
    const editing = Boolean(product);
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">CATALOG</p><h2>${editing ? 'Edit product' : 'Add product'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="productForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(product?.id || '')}"><label class="span-two">Product name<input name="name" maxlength="140" value="${escapeHtml(product?.name || '')}" required></label><label class="span-two">Description<textarea name="description" rows="3" maxlength="3000">${escapeHtml(product?.description || '')}</textarea></label><label>Price<input name="price" type="number" min="0" step="0.01" value="${escapeHtml(product?.price ?? '')}" required></label><label>Discount price<input name="discountPrice" type="number" min="0" step="0.01" value="${escapeHtml(product?.discountPrice || '')}"></label><label>Stock quantity<input name="stock" type="number" min="0" step="1" value="${escapeHtml(product?.stock ?? 0)}" required></label><label>Category<select name="categoryId"><option value="">Uncategorized</option>${categories.map(item=>`<option value="${item.id}"${item.id === product?.categoryId ? ' selected' : ''}>${escapeHtml(item.name)}</option>`).join('')}</select></label><label class="span-two">Product image<input name="image" type="file" accept="image/*"><small>${editing ? 'Leave empty to keep the current image.' : 'Image stays in this browser.'}</small></label><label class="check-label"><input name="featured" type="checkbox"${product?.featured ? ' checked' : ''}> Featured product</label><label class="check-label"><input name="enabled" type="checkbox"${product?.enabled !== false ? ' checked' : ''}> Enabled</label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">${editing ? 'Save product' : 'Create product'}</button></div></form>`;
    $('#recordDialog').showModal();
  }

  async function renderOrders() {
    setPage('Orders', 'Review purchases, payment status, and fulfillment.', '<button class="button primary" data-action="new-order">＋ Record order</button>');
    const [orders, store] = await Promise.all([getState('orders'), getState('store')]);
    $('#view').innerHTML = `<section class="panel table-panel"><div class="toolbar"><div class="search-field"><span>⌕</span><input id="orderSearch" type="search" placeholder="Search order or customer" aria-label="Search orders"></div><select id="orderStatusFilter" class="filter-select"><option value="">All statuses</option>${['Pending','Processing','Shipped','Delivered','Cancelled'].map(status=>`<option>${status}</option>`).join('')}</select><label class="date-filter">From<input id="orderFrom" type="date" aria-label="Orders from date"></label><label class="date-filter">To<input id="orderTo" type="date" aria-label="Orders to date"></label><span class="toolbar-count" id="orderCount"></span></div><div class="table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Date</th><th>Payment</th><th>Total</th><th>Status</th><th>Actions</th></tr></thead><tbody id="orderRows"></tbody></table></div></section>`;
    const draw = () => {
      const query = $('#orderSearch').value.trim().toLowerCase(), status = $('#orderStatusFilter').value, from = $('#orderFrom').value, to = $('#orderTo').value;
      const matches = orders.slice().sort((a,b)=>new Date(b.createdAt)-new Date(a.createdAt)).filter(order => (!status || order.status === status) && (!from || dayKey(order.createdAt) >= from) && (!to || dayKey(order.createdAt) <= to) && ` ${order.number} ${order.customerName} ${order.customerEmail}`.toLowerCase().includes(query));
      $('#orderRows').innerHTML = matches.map(order=>`<tr><td><b>#${escapeHtml(order.number)}</b></td><td>${escapeHtml(order.customerName)}<small>${escapeHtml(order.customerEmail)}</small></td><td>${dateText(order.createdAt)}</td><td><span class="state-chip ${order.paymentStatus === 'Paid' ? 'positive' : 'neutral'}">${escapeHtml(order.paymentStatus)}</span></td><td>${formatMoney(order.total, store.currency)}</td><td><select class="inline-status" data-action="order-status" data-id="${order.id}" aria-label="Change status for order ${escapeHtml(order.number)}">${['Pending','Processing','Shipped','Delivered','Cancelled'].map(value=>`<option${value === order.status ? ' selected' : ''}>${value}</option>`).join('')}</select></td><td><button class="icon-button" title="View order details" aria-label="View order details" data-action="view-order" data-id="${order.id}">↗</button></td></tr>`).join('') || tableEmpty(7,'No orders match these filters.');
      $('#orderCount').textContent = `${matches.length} orders`;
    };
    for (const selector of ['#orderSearch','#orderStatusFilter','#orderFrom','#orderTo']) $(selector).addEventListener(selector === '#orderSearch' ? 'input' : 'change',draw);
    draw();
  }

  async function openOrderForm() {
    const [customers, products, store] = await Promise.all([getState('customers'), getState('products'), getState('store')]);
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">ORDER MANAGEMENT</p><h2>Record order</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div>${customers.length && products.length ? `<form id="orderForm" class="form-grid"><label class="span-two">Customer<select name="customerId" required>${customers.map(item=>`<option value="${item.id}">${escapeHtml(item.name)} · ${escapeHtml(item.email)}</option>`).join('')}</select></label><label class="span-two">Product<select name="productId" required>${products.map(item=>`<option value="${item.id}" data-price="${Number(item.discountPrice) || Number(item.price)}" data-name="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${formatMoney(item.discountPrice || item.price,store.currency)} · ${item.stock} in stock</option>`).join('')}</select></label><label>Quantity<input name="quantity" type="number" min="1" value="1" required></label><label>Payment status<select name="paymentStatus">${(store.paymentStatuses || ['Pending','Paid','Refunded']).map(item=>`<option>${escapeHtml(item)}</option>`).join('')}</select></label><label class="span-two">Shipping address<input name="shippingAddress" maxlength="300" required></label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save order</button></div></form>` : emptyState('Add a customer and product first','Orders need a customer and an item in the local catalog.')} `;
    $('#recordDialog').showModal();
  }

  function showOrder(order, currency) {
    const lines = (order.items || []).map(item=>`<tr><td>${escapeHtml(item.name)}</td><td>${Number(item.quantity)}</td><td>${formatMoney(item.price,currency)}</td><td>${formatMoney(Number(item.price)*Number(item.quantity),currency)}</td></tr>`).join('');
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">ORDER DETAILS</p><h2>Order #${escapeHtml(order.number)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><div class="status-list"><div><span>Customer</span><b>${escapeHtml(order.customerName)} · ${escapeHtml(order.customerEmail)}</b></div><div><span>Placed</span><b>${dateText(order.createdAt)}</b></div><div><span>Payment</span><b>${escapeHtml(order.paymentStatus)}</b></div><div><span>Shipping</span><b>${escapeHtml(order.shippingAddress)}</b></div></div><div class="table-wrap"><table><thead><tr><th>Product</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead><tbody>${lines}</tbody></table></div><p class="order-total">Order total <b>${formatMoney(order.total,currency)}</b></p><div class="dialog-actions"><button class="button secondary" data-action="close-modal">Close</button><button class="button quiet-danger" data-action="cancel-order" data-id="${order.id}"${order.status === 'Cancelled' ? ' disabled' : ''}>Cancel order</button></div>`;
    $('#recordDialog').showModal();
  }

  async function renderCustomers() {
    setPage('Customers', 'Manage customer records and review purchase history.', '<button class="button primary" data-action="new-customer">＋ Add customer</button>');
    const [customers, orders] = await Promise.all([getState('customers'), getState('orders')]);
    $('#view').innerHTML = `<section class="panel table-panel"><div class="toolbar"><div class="search-field"><span>⌕</span><input id="customerSearch" type="search" placeholder="Search name or email" aria-label="Search customers"></div><span class="toolbar-count" id="customerCount"></span></div><div class="table-wrap"><table><thead><tr><th>Customer</th><th>Phone</th><th>Orders</th><th>Lifetime purchases</th><th>Joined</th><th>Actions</th></tr></thead><tbody id="customerRows"></tbody></table></div></section>`;
    const draw = async () => {
      const query = $('#customerSearch').value.trim().toLowerCase(), store = await getState('store');
      const matches = customers.filter(customer=>`${customer.name} ${customer.email} ${customer.phone || ''}`.toLowerCase().includes(query));
      $('#customerRows').innerHTML = matches.map(customer=>{const purchases=orders.filter(order=>order.customerId===customer.id&&order.status!=='Cancelled');const total=purchases.reduce((sum,order)=>sum+Number(order.total||0),0);return `<tr><td><div class="identity-cell"><span class="avatar">${escapeHtml(customer.name.slice(0,1).toUpperCase())}</span><div><b>${escapeHtml(customer.name)}</b><small>${escapeHtml(customer.email)}</small></div></div></td><td>${escapeHtml(customer.phone || '—')}</td><td>${purchases.length}</td><td>${formatMoney(total,store.currency)}</td><td>${dateText(customer.createdAt)}</td><td class="actions-cell"><button class="icon-button" title="View customer profile" aria-label="View customer profile" data-action="view-customer" data-id="${customer.id}">↗</button><button class="icon-button" title="Edit customer" aria-label="Edit customer" data-action="edit-customer" data-id="${customer.id}">✎</button><button class="icon-button danger-icon" title="Delete customer" aria-label="Delete customer" data-action="delete-customer" data-id="${customer.id}">×</button></td></tr>`}).join('') || tableEmpty(6,'No customers match your search.');
      $('#customerCount').textContent = `${matches.length} customers`;
    };
    $('#customerSearch').addEventListener('input',()=>draw().catch(showError)); draw();
  }

  function openCustomerForm(customer = null) {
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">CUSTOMER DIRECTORY</p><h2>${customer ? 'Edit customer' : 'Add customer'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="customerForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(customer?.id || '')}"><label class="span-two">Full name<input name="name" maxlength="120" value="${escapeHtml(customer?.name || '')}" required></label><label>Email<input name="email" type="email" maxlength="180" value="${escapeHtml(customer?.email || '')}" required></label><label>Phone<input name="phone" type="tel" maxlength="40" value="${escapeHtml(customer?.phone || '')}"></label><label class="span-two">Address<textarea name="address" rows="2" maxlength="500">${escapeHtml(customer?.address || '')}</textarea></label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save customer</button></div></form>`;
    $('#recordDialog').showModal();
  }

  async function showCustomer(customer) {
    const [orders, store] = await Promise.all([getState('orders'),getState('store')]);
    const history=orders.filter(order=>order.customerId===customer.id).sort((a,b)=>new Date(b.createdAt)-new Date(a.createdAt));
    $('#modalContent').innerHTML=`<div class="dialog-head"><div><p class="eyebrow">CUSTOMER PROFILE</p><h2>${escapeHtml(customer.name)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><div class="profile-hero"><span class="avatar avatar-large">${escapeHtml(customer.name.slice(0,1).toUpperCase())}</span><div><b>${escapeHtml(customer.email)}</b><span>${escapeHtml(customer.phone || 'No phone')}</span></div></div><dl class="profile-details"><div><dt>Address</dt><dd>${escapeHtml(customer.address || '—')}</dd></div><div><dt>Customer since</dt><dd>${dateText(customer.createdAt)}</dd></div><div><dt>Orders</dt><dd>${history.length}</dd></div><div><dt>Total purchases</dt><dd>${formatMoney(history.filter(order=>order.status!=='Cancelled').reduce((sum,order)=>sum+Number(order.total||0),0),store.currency)}</dd></div></dl><h3 class="subheading">Order history</h3><div class="table-wrap"><table><thead><tr><th>Order</th><th>Date</th><th>Total</th><th>Status</th></tr></thead><tbody>${history.map(order=>`<tr><td>#${escapeHtml(order.number)}</td><td>${dateText(order.createdAt)}</td><td>${formatMoney(order.total,store.currency)}</td><td>${escapeHtml(order.status)}</td></tr>`).join('')||tableEmpty(4,'No orders yet.')}</tbody></table></div>`;
    $('#recordDialog').showModal();
  }

  async function renderCategories() {
    setPage('Categories', 'Organize catalog sections and control visibility.', '<button class="button primary" data-action="new-category">＋ Add category</button>');
    const [categories,products] = await Promise.all([getState('categories'),getState('products')]);
    $('#view').innerHTML=`<section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Category</th><th>Description</th><th>Products</th><th>Visibility</th><th>Actions</th></tr></thead><tbody>${categories.map(item=>`<tr><td><b>${escapeHtml(item.name)}</b></td><td>${escapeHtml(item.description || '—')}</td><td>${products.filter(product=>product.categoryId===item.id).length}</td><td><span class="state-chip ${item.visible?'positive':'neutral'}">${item.visible?'Visible':'Hidden'}</span></td><td class="actions-cell"><button class="icon-button" title="Edit category" aria-label="Edit category" data-action="edit-category" data-id="${item.id}">✎</button><button class="icon-button" title="Toggle visibility" aria-label="Toggle visibility" data-action="toggle-category" data-id="${item.id}">${item.visible?'Ⅱ':'▶'}</button><button class="icon-button danger-icon" title="Delete category" aria-label="Delete category" data-action="delete-category" data-id="${item.id}">×</button></td></tr>`).join('')||tableEmpty(5,'No categories yet. Add one to organize products.')}</tbody></table></div></section>`;
  }

  function openCategoryForm(category=null) {
    $('#modalContent').innerHTML=`<div class="dialog-head"><div><p class="eyebrow">PRODUCT CATEGORIES</p><h2>${category?'Edit category':'Add category'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="categoryForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(category?.id||'')}"><label class="span-two">Name<input name="name" maxlength="90" value="${escapeHtml(category?.name||'')}" required></label><label class="span-two">Description<textarea name="description" rows="3" maxlength="500">${escapeHtml(category?.description||'')}</textarea></label><label class="span-two">Category image<input name="image" type="file" accept="image/*"><small>${category?'Leave empty to keep the current image.':'Image stays in this browser.'}</small></label><label class="check-label"><input name="visible" type="checkbox"${category?.visible!==false?' checked':''}> Visible on store</label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save category</button></div></form>`;
    $('#recordDialog').showModal();
  }

  async function renderCoupons() {
    setPage('Coupons', 'Create and manage discount codes and usage limits.', '<button class="button primary" data-action="new-coupon">＋ Create coupon</button>');
    const [coupons,store]=await Promise.all([getState('coupons'),getState('store')]);
    $('#view').innerHTML=`<section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Code</th><th>Discount</th><th>Minimum order</th><th>Expires</th><th>Usage</th><th>Status</th><th>Actions</th></tr></thead><tbody>${coupons.map(item=>`<tr><td><b>${escapeHtml(item.code)}</b></td><td>${item.type==='percent'?`${Number(item.value)}%`:formatMoney(item.value,store.currency)}</td><td>${formatMoney(item.minimumOrder,store.currency)}</td><td>${item.expiresAt?dateText(item.expiresAt):'No expiry'}</td><td>${Number(item.used)||0}${item.usageLimit?` / ${item.usageLimit}`:''}</td><td><span class="state-chip ${item.enabled?'positive':'neutral'}">${item.enabled?'Enabled':'Disabled'}</span></td><td class="actions-cell"><button class="icon-button" title="Edit coupon" aria-label="Edit coupon" data-action="edit-coupon" data-id="${item.id}">✎</button><button class="icon-button" title="Toggle coupon" aria-label="Toggle coupon" data-action="toggle-coupon" data-id="${item.id}">${item.enabled?'Ⅱ':'▶'}</button><button class="icon-button danger-icon" title="Delete coupon" aria-label="Delete coupon" data-action="delete-coupon" data-id="${item.id}">×</button></td></tr>`).join('')||tableEmpty(7,'No coupons created yet.')}</tbody></table></div></section>`;
  }

  function openCouponForm(coupon=null) {
    $('#modalContent').innerHTML=`<div class="dialog-head"><div><p class="eyebrow">DISCOUNTS</p><h2>${coupon?'Edit coupon':'Create coupon'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="couponForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(coupon?.id||'')}"><label>Coupon code<input name="code" maxlength="40" value="${escapeHtml(coupon?.code||'')}" pattern="[A-Za-z0-9_-]+" required></label><label>Discount type<select name="type"><option value="percent"${coupon?.type!=='fixed'?' selected':''}>Percentage</option><option value="fixed"${coupon?.type==='fixed'?' selected':''}>Fixed amount</option></select></label><label>Discount value<input name="value" type="number" min="0.01" step="0.01" value="${escapeHtml(coupon?.value??'')}" required></label><label>Minimum order<input name="minimumOrder" type="number" min="0" step="0.01" value="${escapeHtml(coupon?.minimumOrder??0)}"></label><label>Expiry date<input name="expiresAt" type="date" value="${escapeHtml(coupon?.expiresAt||'')}"></label><label>Usage limit<input name="usageLimit" type="number" min="0" step="1" value="${escapeHtml(coupon?.usageLimit||'')}" placeholder="Unlimited"></label><label class="check-label"><input name="enabled" type="checkbox"${coupon?.enabled!==false?' checked':''}> Enabled</label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save coupon</button></div></form>`;
    $('#recordDialog').showModal();
  }

  async function renderReports() {
    setPage('Reports & analytics', 'Analyze revenue, orders, products, and customer growth.', '<button class="button secondary" data-action="export-report">Export CSV ↗</button>');
    const [orders,customers,products,store]=await Promise.all([getState('orders'),getState('customers'),getState('products'),getState('store')]);
    const now=new Date(), periods=[['Today',0],['7 days',7],['30 days',30],['12 months',365]];
    const revenueFor=days=>orders.filter(order=>order.status!=='Cancelled'&&new Date(order.createdAt)>=new Date(now.getTime()-days*86400000)).reduce((sum,order)=>sum+Number(order.total||0),0);
    const chart=Array.from({length:12},(_,index)=>{const date=new Date(now.getFullYear(),now.getMonth()-11+index,1),key=`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}`;return {key,short:date.toLocaleDateString([],{month:'short'}),label:date.toLocaleDateString([],{month:'long',year:'numeric'}),value:orders.filter(order=>order.status!=='Cancelled'&&String(order.createdAt).slice(0,7)===key).reduce((sum,order)=>sum+Number(order.total||0),0)}});
    const salesRows=periods.map(([label,days])=>{const relevant=days?orders.filter(order=>order.status!=='Cancelled'&&new Date(order.createdAt)>=new Date(now.getTime()-days*86400000)):orders.filter(order=>order.status!=='Cancelled'&&new Date(order.createdAt).getFullYear()===now.getFullYear());return `<tr><td>${label}</td><td>${relevant.length}</td><td>${formatMoney(relevant.reduce((sum,order)=>sum+Number(order.total||0),0),store.currency)}</td></tr>`}).join('');
    const sold=new Map();for(const order of orders.filter(item=>item.status!=='Cancelled'))for(const item of order.items||[])sold.set(item.productId,(sold.get(item.productId)||0)+Number(item.quantity||0));
    $('#view').innerHTML=`<div class="metrics-grid">${periods.slice(1).map(([label,days])=>metricCard(`${label} revenue`,formatMoney(revenueFor(days),store.currency),'Completed and active orders','$')).join('')}${metricCard('Customers',customers.length,'Registered local customers','♙','tone-cyan')}</div><div class="dashboard-grid"><section class="panel chart-panel"><div class="panel-heading"><div><p class="eyebrow">REVENUE</p><h2>Monthly sales</h2></div><span class="period-label">Last 12 months</span></div>${barsSvg(chart,'Revenue')}</section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">SALES SUMMARY</p><h2>Period breakdown</h2></div></div><div class="table-wrap"><table><thead><tr><th>Period</th><th>Orders</th><th>Revenue</th></tr></thead><tbody>${salesRows}</tbody></table></div></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">PRODUCT PERFORMANCE</p><h2>Units sold</h2></div></div><div class="status-list">${products.slice().sort((a,b)=>(sold.get(b.id)||0)-(sold.get(a.id)||0)).slice(0,10).map(product=>`<div><span>${escapeHtml(product.name)}</span><b>${sold.get(product.id)||0} sold</b></div>`).join('')||'<p class="muted small">No products to report.</p>'}</div></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">CUSTOMER GROWTH</p><h2>New customers</h2></div></div><div class="status-list">${periods.slice(1).map(([label,days])=>`<div><span>${label}</span><b>${customers.filter(customer=>new Date(customer.createdAt)>=new Date(now.getTime()-days*86400000)).length}</b></div>`).join('')}</div></section></div>`;
  }

  function userRow(user) {
    const statusClass = user.status === 'active' ? 'positive' : 'neutral';
    return `<tr><td><div class="identity-cell"><span class="avatar">${escapeHtml((user.name || '?').slice(0,1).toUpperCase())}</span><div><b>${escapeHtml(user.name)}</b><small>${escapeHtml(user.email)}</small></div></div></td><td><span class="role-chip">${escapeHtml(user.role)}</span></td><td><span class="state-chip ${statusClass}">${escapeHtml(user.status)}</span></td><td>${escapeHtml(user.department || '—')}</td><td>${dateText(user.createdAt)}</td><td class="actions-cell"><button class="icon-button" title="View profile" aria-label="View profile" data-action="view-user" data-id="${user.id}">↗</button><button class="icon-button" title="Edit user" aria-label="Edit user" data-action="edit-user" data-id="${user.id}">✎</button><button class="icon-button" title="Toggle account status" aria-label="Toggle account status" data-action="toggle-user" data-id="${user.id}">${user.status === 'active' ? 'Ⅱ' : '▶'}</button><button class="icon-button danger-icon" title="Delete user" aria-label="Delete user" data-action="delete-user" data-id="${user.id}">×</button></td></tr>`;
  }

  async function renderUsers() {
    setPage('Users', 'Manage local account records and access roles.', '<button class="button primary" data-action="new-user"><span aria-hidden="true">＋</span> Add user</button>');
    const users = await getState('users');
    $('#view').innerHTML = `<section class="panel table-panel"><div class="toolbar"><div class="search-field"><span>⌕</span><input id="userSearch" type="search" placeholder="Search name or email" aria-label="Search users"></div><select id="userStatus" class="filter-select" aria-label="Filter by status"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select><select id="userRole" class="filter-select" aria-label="Filter by role"><option value="">All roles</option><option>Administrator</option><option>Editor</option><option>User</option></select><span class="toolbar-count" id="userCount"></span></div><div class="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Department</th><th>Added</th><th>Actions</th></tr></thead><tbody id="userRows"></tbody></table></div><div class="table-foot">Local account directory · ${users.length} records</div></section>`;
    const draw = () => {
      const query = $('#userSearch').value.trim().toLowerCase();
      const status = $('#userStatus').value;
      const role = $('#userRole').value;
      const matches = users.filter(user => (!status || user.status === status) && (!role || user.role === role) && `${user.name} ${user.email} ${user.department || ''}`.toLowerCase().includes(query));
      $('#userRows').innerHTML = matches.map(userRow).join('') || tableEmpty(6, 'No matching users. Use Add user to create a local record.');
      $('#userCount').textContent = `${matches.length} shown`;
    };
    $('#userSearch').addEventListener('input', draw);
    $('#userStatus').addEventListener('change', draw);
    $('#userRole').addEventListener('change', draw);
    draw();
  }

  function openUserForm(user = null) {
    const editing = Boolean(user);
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">USER DIRECTORY</p><h2>${editing ? 'Edit user' : 'Add user'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="userForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(user?.id || '')}"><label class="span-two">Full name<input name="name" value="${escapeHtml(user?.name || '')}" maxlength="100" required></label><label>Email<input name="email" type="email" value="${escapeHtml(user?.email || '')}" maxlength="180" required></label><label>Department<input name="department" value="${escapeHtml(user?.department || '')}" maxlength="100"></label><label>Role<select name="role"><option${user?.role === 'User' ? ' selected' : ''}>User</option><option${user?.role === 'Editor' ? ' selected' : ''}>Editor</option><option${user?.role === 'Administrator' ? ' selected' : ''}>Administrator</option></select></label><label>Status<select name="status"><option value="active"${!user || user.status === 'active' ? ' selected' : ''}>Active</option><option value="inactive"${user?.status === 'inactive' ? ' selected' : ''}>Inactive</option></select></label><label class="span-two">Profile notes<textarea name="notes" rows="3" maxlength="1200">${escapeHtml(user?.notes || '')}</textarea></label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">${editing ? 'Save changes' : 'Create user'}</button></div></form>`;
    $('#recordDialog').showModal();
  }

  function showUserProfile(user) {
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">ACCOUNT PROFILE</p><h2>${escapeHtml(user.name)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><div class="profile-hero"><span class="avatar avatar-large">${escapeHtml((user.name || '?').slice(0,1).toUpperCase())}</span><div><b>${escapeHtml(user.email)}</b><span class="state-chip ${user.status === 'active' ? 'positive' : 'neutral'}">${escapeHtml(user.status)}</span></div></div><dl class="profile-details"><div><dt>Role</dt><dd>${escapeHtml(user.role)}</dd></div><div><dt>Department</dt><dd>${escapeHtml(user.department || '—')}</dd></div><div><dt>Created</dt><dd>${dateText(user.createdAt)}</dd></div><div><dt>Last login</dt><dd>${dateText(user.lastLoginAt)}</dd></div><div class="span-two"><dt>Notes</dt><dd>${escapeHtml(user.notes || 'No profile notes.')}</dd></div></dl><div class="dialog-actions"><button class="button secondary" data-action="close-modal">Close</button><button class="button primary" data-action="edit-user" data-id="${user.id}">Edit profile</button></div>`;
    $('#recordDialog').showModal();
  }

  function releaseRow(release) {
    return `<tr><td><div class="release-title"><b>${escapeHtml(release.version)}</b>${release.isLatest ? '<span class="latest-mark">LATEST</span>' : ''}<small>${escapeHtml(release.fileName)}</small></div></td><td>${escapeHtml(release.platform)}</td><td>${formatBytes(release.fileSize)}</td><td>${dateText(release.uploadedAt)}</td><td>${Number(release.downloads) || 0}</td><td><span class="state-chip ${release.status === 'published' ? 'positive' : 'neutral'}">${escapeHtml(release.status)}</span></td><td class="actions-cell"><button class="icon-button" title="Download package" aria-label="Download package" data-action="download-release" data-id="${release.id}">↓</button><button class="icon-button" title="Copy temporary link" aria-label="Copy temporary link" data-action="copy-release-link" data-id="${release.id}">⛓</button><button class="icon-button" title="Edit release" aria-label="Edit release" data-action="edit-release" data-id="${release.id}">✎</button><button class="icon-button danger-icon" title="Delete release" aria-label="Delete release" data-action="delete-release" data-id="${release.id}">×</button></td></tr>`;
  }

  async function renderReleases() {
    setPage('Software & releases', 'Keep local package versions and release notes in one place.', '<button class="button primary" data-action="new-release"><span aria-hidden="true">＋</span> Add release</button>');
    const releases = await getState('releases');
    const published = releases.filter(release => release.status === 'published').length;
    const totalSize = releases.reduce((sum, release) => sum + (release.fileSize || 0), 0);
    $('#view').innerHTML = `<div class="metrics-grid compact-metrics">${metricCard('Versions', releases.length, 'Stored in this browser', '⬡')}${metricCard('Published', published, 'Available in local release list', '◉', 'tone-blue')}${metricCard('Package storage', formatBytes(totalSize), 'Release files only', '▧', 'tone-violet')}</div><section class="panel table-panel"><div class="panel-heading"><div><p class="eyebrow">VERSION HISTORY</p><h2>All releases</h2></div><div class="toolbar"><input id="releaseSearch" class="search-compact" type="search" placeholder="Search versions" aria-label="Search releases"><select id="releaseFilter" class="filter-select"><option value="">All statuses</option><option value="published">Published</option><option value="draft">Draft</option></select></div></div><div class="table-wrap"><table><thead><tr><th>Version / package</th><th>Platform</th><th>Size</th><th>Uploaded</th><th>Downloads</th><th>Status</th><th>Actions</th></tr></thead><tbody id="releaseRows"></tbody></table></div></section><p class="notice-line">Download links are generated locally and work only while this browser session is open. No files are uploaded to a server.</p>`;
    const draw = () => {
      const query = $('#releaseSearch').value.toLowerCase();
      const filter = $('#releaseFilter').value;
      const matches = releases.filter(item => (!filter || item.status === filter) && `${item.version} ${item.fileName} ${item.platform}`.toLowerCase().includes(query));
      $('#releaseRows').innerHTML = matches.map(releaseRow).join('') || tableEmpty(7, 'No releases yet. Add an EXE or ZIP package to start a version history.');
    };
    $('#releaseSearch').addEventListener('input', draw);
    $('#releaseFilter').addEventListener('change', draw);
    draw();
  }

  function openReleaseForm(release = null) {
    const editing = Boolean(release);
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">PACKAGE LIBRARY</p><h2>${editing ? 'Edit release' : 'Add software release'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="releaseForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(release?.id || '')}"><label>Version<input name="version" placeholder="1.0.0" value="${escapeHtml(release?.version || '')}" pattern="\\d+\\.\\d+(\\.\\d+)?" required></label><label>Platform<select name="platform"><option${release?.platform === 'Windows' ? ' selected' : ''}>Windows</option><option${release?.platform === 'Android' ? ' selected' : ''}>Android</option><option${release?.platform === 'Other' ? ' selected' : ''}>Other</option></select></label><label class="span-two">Package file ${editing ? '<small>(leave empty to keep current file)</small>' : ''}<input name="package" type="file" accept=".exe,.zip,application/zip,application/x-msdownload" ${editing ? '' : 'required'}></label><label>Minimum version<input name="minVersion" value="${escapeHtml(release?.minVersion || '')}" placeholder="Optional"></label><label>Status<select name="status"><option value="draft"${!release || release.status === 'draft' ? ' selected' : ''}>Draft</option><option value="published"${release?.status === 'published' ? ' selected' : ''}>Published</option></select></label><label class="span-two">Release notes<textarea name="notes" rows="4" maxlength="3000">${escapeHtml(release?.notes || '')}</textarea></label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">${editing ? 'Save release' : 'Save draft'}</button></div></form>`;
    $('#recordDialog').showModal();
  }

  async function addFiles(fileList) {
    const selected = [...fileList];
    if (!selected.length) return;
    const files = await getState('files');
    let added = 0;
    for (const file of selected) {
      const id = uid();
      await putBlob(id, file);
      files.unshift({id, name:file.name, type:file.type || 'application/octet-stream', size:file.size, category:'Unsorted', createdAt:new Date().toISOString(), modified:file.lastModified || Date.now()});
      added += 1;
    }
    await setState('files', files);
    await recordActivity('Files added', `${added} item${added === 1 ? '' : 's'} · ${formatBytes(selected.reduce((sum, file) => sum + file.size, 0))}`);
    toast(`${added} file${added === 1 ? '' : 's'} added to local library.`, 'success');
    renderFiles();
  }

  function fileRow(file) {
    return `<tr><td><div class="file-name"><span class="file-type">${escapeHtml(file.type.split('/')[0].slice(0,3).toUpperCase() || 'FILE')}</span><div><b>${escapeHtml(file.name)}</b><small>${escapeHtml(file.type)}</small></div></div></td><td><select class="category-select" data-action="file-category" data-id="${file.id}" aria-label="File category"><option${file.category === 'Unsorted' ? ' selected' : ''}>Unsorted</option><option${file.category === 'Software' ? ' selected' : ''}>Software</option><option${file.category === 'Documents' ? ' selected' : ''}>Documents</option><option${file.category === 'Images' ? ' selected' : ''}>Images</option><option${file.category === 'Other' ? ' selected' : ''}>Other</option></select></td><td>${formatBytes(file.size)}</td><td>${dateText(file.createdAt)}</td><td class="actions-cell"><button class="icon-button" title="Preview file information" aria-label="Preview file information" data-action="preview-file" data-id="${file.id}">◉</button><button class="icon-button" title="Download file" aria-label="Download file" data-action="download-file" data-id="${file.id}">↓</button><button class="icon-button danger-icon" title="Delete file" aria-label="Delete file" data-action="delete-file" data-id="${file.id}">×</button></td></tr>`;
  }

  async function renderFiles() {
    setPage('File library', 'Organize files locally. Originals never leave this browser.', '<button class="button primary" data-action="choose-files"><span aria-hidden="true">＋</span> Add files</button>');
    const files = await getState('files');
    const used = files.reduce((sum, file) => sum + (file.size || 0), 0);
    const categories = [...new Set(files.map(file => file.category))].length;
    $('#view').innerHTML = `<div class="metrics-grid compact-metrics">${metricCard('Library items', files.length, `${categories} categories`, '▧')}${metricCard('Storage used', formatBytes(used), 'Files stored in IndexedDB', '◫', 'tone-blue')}${metricCard('Largest file', formatBytes(Math.max(0, ...files.map(file => file.size || 0))), 'In this browser', '⌗', 'tone-violet')}</div><input id="filesInput" type="file" multiple hidden><section class="panel table-panel"><div class="toolbar"><div class="search-field"><span>⌕</span><input id="fileSearch" type="search" placeholder="Search files" aria-label="Search files"></div><select id="fileCategoryFilter" class="filter-select"><option value="">All categories</option><option>Unsorted</option><option>Software</option><option>Documents</option><option>Images</option><option>Other</option></select><span class="toolbar-count">${files.length} items</span></div><div class="table-wrap"><table><thead><tr><th>File</th><th>Category</th><th>Size</th><th>Added</th><th>Actions</th></tr></thead><tbody id="fileRows"></tbody></table></div></section><p class="notice-line">Browser storage has device-specific limits. Export a backup from Settings before clearing browser data.</p>`;
    const draw = () => {
      const query = $('#fileSearch').value.toLowerCase();
      const category = $('#fileCategoryFilter').value;
      const matches = files.filter(file => (!category || file.category === category) && `${file.name} ${file.type} ${file.category}`.toLowerCase().includes(query));
      $('#fileRows').innerHTML = matches.map(fileRow).join('') || tableEmpty(5, 'No files match. Add files to start your local library.');
    };
    $('#fileSearch').addEventListener('input', draw);
    $('#fileCategoryFilter').addEventListener('change', draw);
    $('#filesInput').addEventListener('change', event => addFiles(event.target.files).catch(showError));
    draw();
  }

  async function previewFile(file) {
    const saved = await getBlob(file.id);
    if (!saved) throw new Error('The file data is missing from browser storage.');
    const isImage = file.type.startsWith('image/');
    temporaryObjectUrl = URL.createObjectURL(saved.blob);
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">FILE DETAILS</p><h2>${escapeHtml(file.name)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div>${isImage ? `<img class="file-preview-image" src="${temporaryObjectUrl}" alt="Preview of ${escapeHtml(file.name)}">` : ''}<dl class="profile-details"><div><dt>Type</dt><dd>${escapeHtml(file.type)}</dd></div><div><dt>Size</dt><dd>${formatBytes(file.size)}</dd></div><div><dt>Category</dt><dd>${escapeHtml(file.category)}</dd></div><div><dt>Added</dt><dd>${dateText(file.createdAt)}</dd></div><div><dt>Modified</dt><dd>${dateText(file.modified)}</dd></div></dl><div class="dialog-actions"><button class="button secondary" data-action="close-modal">Close</button><button class="button primary" data-action="download-file" data-id="${file.id}">Download</button></div>`;
    $('#recordDialog').showModal();
  }

  function announcementRow(item) {
    return `<article class="announcement-row"><div class="announcement-symbol">${item.kind === 'News' ? 'N' : item.kind === 'Update' ? '↗' : '!'}</div><div class="announcement-body"><div class="announcement-meta"><span class="role-chip">${escapeHtml(item.kind)}</span><span class="state-chip ${item.status === 'published' ? 'positive' : 'neutral'}">${escapeHtml(item.status)}</span><time>${dateText(item.createdAt)}</time></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.body)}</p></div><div class="announcement-actions"><button class="icon-button" title="Edit" aria-label="Edit" data-action="edit-announcement" data-id="${item.id}">✎</button><button class="icon-button" title="Toggle publication" aria-label="Toggle publication" data-action="toggle-announcement" data-id="${item.id}">${item.status === 'published' ? 'Ⅱ' : '▶'}</button><button class="icon-button danger-icon" title="Delete" aria-label="Delete" data-action="delete-announcement" data-id="${item.id}">×</button></div></article>`;
  }

  async function renderAnnouncements() {
    setPage('Announcements', 'Draft and publish local news, updates, and service notices.', '<button class="button primary" data-action="new-announcement"><span aria-hidden="true">＋</span> New announcement</button>');
    const items = await getState('announcements');
    $('#view').innerHTML = `<section class="panel"><div class="panel-heading"><div><p class="eyebrow">NEWSROOM</p><h2>Announcements & updates</h2></div><span class="panel-caption">${items.filter(item => item.status === 'published').length} published</span></div><div class="announcement-list">${items.map(announcementRow).join('') || emptyState('Nothing published yet', 'Create an announcement or news item. Drafts remain private to this local dashboard.')}</div></section>`;
  }

  function openAnnouncementForm(item = null) {
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">NEWSROOM</p><h2>${item ? 'Edit announcement' : 'New announcement'}</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="announcementForm" class="form-grid"><input type="hidden" name="id" value="${escapeHtml(item?.id || '')}"><label class="span-two">Title<input name="title" maxlength="160" value="${escapeHtml(item?.title || '')}" required></label><label>Type<select name="kind"><option${item?.kind === 'Announcement' ? ' selected' : ''}>Announcement</option><option${item?.kind === 'Update' ? ' selected' : ''}>Update</option><option${item?.kind === 'News' ? ' selected' : ''}>News</option></select></label><label>Status<select name="status"><option value="draft"${!item || item.status === 'draft' ? ' selected' : ''}>Draft</option><option value="published"${item?.status === 'published' ? ' selected' : ''}>Published</option></select></label><label class="span-two">Message<textarea name="body" rows="5" maxlength="4000" required>${escapeHtml(item?.body || '')}</textarea></label><div class="dialog-actions span-two"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save item</button></div></form>`;
    $('#recordDialog').showModal();
  }

  function previewWebsite(content) {
    return `<div class="site-preview"><div class="preview-top"><span class="preview-brand">AURIX</span><span>LOCAL PREVIEW</span></div>${content.announcement ? `<div class="preview-banner">${escapeHtml(content.announcement)}</div>` : ''}<section class="preview-hero"><p class="eyebrow">PRIVATE WORKSPACE</p><h2>${escapeHtml(content.title || 'AURIX')}</h2><h3>${escapeHtml(content.tagline)}</h3><p>${escapeHtml(content.hero)}</p><button class="button primary" type="button" disabled>Download section preview</button></section>${content.comingSoon ? `<section class="preview-section"><span class="state-chip neutral">COMING SOON</span><p>${escapeHtml(content.comingSoon)}</p></section>` : ''}<section class="preview-section"><h3>About</h3><p>${escapeHtml(content.about)}</p><h3>Software</h3><p>${escapeHtml(content.software)}</p><p>${escapeHtml(content.downloadNote)}</p></section><footer class="preview-footer">${escapeHtml(content.footer)} · ${escapeHtml(content.contactEmail)}</footer></div>`;
  }

  async function renderWebsite() {
    setPage('Website content', 'Edit local homepage copy and preview the saved content.', '<button class="button secondary" data-action="export-website">Export content JSON <span aria-hidden="true">↗</span></button>');
    const site = await getState('website');
    $('#view').innerHTML = `<div class="website-layout"><form id="websiteForm" class="panel website-form"><div class="panel-heading"><div><p class="eyebrow">CONTENT EDITOR</p><h2>Homepage settings</h2></div><span class="panel-caption">Saved locally</span></div><div class="form-grid"><label>Website title<input name="title" value="${escapeHtml(site.title)}" maxlength="90" required></label><label>Tagline<input name="tagline" value="${escapeHtml(site.tagline)}" maxlength="140"></label><label class="span-two">Hero introduction<textarea name="hero" rows="3" maxlength="500">${escapeHtml(site.hero)}</textarea></label><label class="span-two">Announcement banner<textarea name="announcement" rows="2" maxlength="300">${escapeHtml(site.announcement)}</textarea></label><label class="span-two">About section<textarea name="about" rows="3" maxlength="1200">${escapeHtml(site.about)}</textarea></label><label class="span-two">Software description<textarea name="software" rows="3" maxlength="900">${escapeHtml(site.software)}</textarea></label><label class="span-two">Coming soon section<textarea name="comingSoon" rows="2" maxlength="500">${escapeHtml(site.comingSoon)}</textarea></label><label class="span-two">Download section note<textarea name="downloadNote" rows="2" maxlength="350">${escapeHtml(site.downloadNote)}</textarea></label><label>Contact email<input name="contactEmail" type="email" value="${escapeHtml(site.contactEmail)}" maxlength="180"></label><label>Footer text<input name="footer" value="${escapeHtml(site.footer)}" maxlength="200"></label><div class="dialog-actions span-two"><button class="button primary" type="submit">Save homepage content</button></div></div></form><section class="panel preview-panel"><div class="panel-heading"><div><p class="eyebrow">PREVIEW</p><h2>Homepage</h2></div><span class="panel-caption">Local only</span></div><div id="websitePreview">${previewWebsite(site)}</div></section></div><section class="panel announcement-summary"><div class="panel-heading"><div><p class="eyebrow">PUBLISHED CONTENT</p><h2>News & updates</h2></div><button class="text-button" data-route="announcements">Manage announcements →</button></div><p class="muted">${(await getState('announcements')).filter(item => item.status === 'published').length} published locally. These records do not update a hosted website.</p></section>`;
    $('#websiteForm').addEventListener('submit', async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      await setState('website', values);
      await recordActivity('Website content saved', 'Homepage copy updated locally');
      $('#websitePreview').innerHTML = previewWebsite(values);
      toast('Homepage content saved locally.', 'success');
    });
  }

  async function renderActivity() {
    setPage('Activity log', 'A local audit trail for this browser.', '<button class="button secondary" data-action="export-activity">Export CSV <span aria-hidden="true">↗</span></button>');
    const [activities, logins] = await Promise.all([getState('activities'), getState('logins')]);
    $('#view').innerHTML = `<div class="dashboard-grid"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">AUDIT TRAIL</p><h2>Recent activity</h2></div><button class="button quiet-danger" data-action="clear-activity">Clear log</button></div><div class="activity-list full-activity">${activityRows(activities, 100)}</div></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">ACCESS HISTORY</p><h2>Admin sign-ins</h2></div><span class="panel-caption">Stored on this device</span></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>Email</th><th>Device</th></tr></thead><tbody>${logins.map(login => `<tr><td>${dateText(login.at)}</td><td>${escapeHtml(login.email)}</td><td>${escapeHtml(login.device || 'This browser')}</td></tr>`).join('') || tableEmpty(3,'No sign-ins yet.')}</tbody></table></div></section></div>`;
  }

  async function renderSettings() {
    setPage('Settings & backup', 'Protect local data and manage this browser session.');
    const auth = readAuth();
    const [blobs, store] = await Promise.all([allBlobs(),getState('store')]);
      $('#view').innerHTML = `<div class="settings-grid"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">STORE PROFILE</p><h2>Store information</h2></div><span class="panel-caption">Saved locally</span></div><form id="storeForm" class="form-grid"><label class="span-two">Website name<input name="name" maxlength="90" value="${escapeHtml(store.name)}" required></label><label>Currency<select name="currency">${['USD','CAD','AUD','GBP','EUR','INR','NZD','SGD'].map(currency=>`<option${store.currency===currency?' selected':''}>${currency}</option>`).join('')}</select></label><label class="span-two">Shipping information<textarea name="shippingInfo" rows="3" maxlength="700">${escapeHtml(store.shippingInfo)}</textarea></label><label class="span-two">Payment status options<input name="paymentStatuses" maxlength="180" value="${escapeHtml((store.paymentStatuses||[]).join(', '))}"><small>Comma-separated values used for new orders.</small></label><div class="dialog-actions span-two"><button class="button primary" type="submit">Save store settings</button></div></form></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">LOCAL SECURITY</p><h2>Administrator access</h2></div><span class="pill live"><i></i>Browser locked</span></div><p class="muted">Password hashes use PBKDF2-SHA-256. Session expires after 30 minutes of inactivity.</p><div class="settings-detail"><span>Administrator</span><b>${escapeHtml(auth?.name || '')} · ${escapeHtml(auth?.email || '')}</b></div><button class="button secondary" data-action="change-password">Change local password</button><button class="button quiet-danger" data-action="logout">Sign out</button><p class="security-warning">Local-only authentication is suitable for a private prototype, not a secure public production admin system. Anyone with access to this browser profile can alter local data.</p></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">DATA PORTABILITY</p><h2>Backup & restore</h2></div><span class="panel-caption">${formatBytes(used)} stored</span></div><p class="muted">Backups include products, orders, customers, categories, coupons, store settings, and existing records. The password hash is not included.</p><div class="button-stack"><button class="button primary" data-action="export-backup">Download full backup</button><label class="button secondary file-button">Restore backup<input id="backupInput" type="file" accept=".json,application/json" hidden></label><button class="button quiet-danger" data-action="clear-data">Clear local records</button></div></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">ABOUT THIS INSTANCE</p><h2>Local operation</h2></div></div><div class="status-list"><div><span>Storage</span><b>IndexedDB <em>Ready</em></b></div><div><span>API connections</span><b>None <em>Disabled</em></b></div><div><span>Browser storage</span><b>${formatBytes(used)} <em>${blobs.length} files</em></b></div></div><p class="muted small">This local demo does not publish changes to the hosted AURIX website.</p></section></div>`;
    const used = blobs.reduce((sum, item) => sum + (item.size || 0), 0);
    $('#view').innerHTML = `<div class="settings-grid"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">LOCAL SECURITY</p><h2>Administrator access</h2></div><span class="pill live"><i></i>Browser locked</span></div><p class="muted">Password hashes use PBKDF2-SHA-256. Session expires after 30 minutes of inactivity.</p><div class="settings-detail"><span>Administrator</span><b>${escapeHtml(auth?.name || '')} · ${escapeHtml(auth?.email || '')}</b></div><button class="button secondary" data-action="change-password">Change local password</button><button class="button quiet-danger" data-action="logout">Sign out</button><p class="security-warning">Local-only authentication is suitable for a private prototype, not a secure public production admin system. Anyone with access to this browser profile can alter local data.</p></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">DATA PORTABILITY</p><h2>Backup & restore</h2></div><span class="panel-caption">${formatBytes(used)} stored</span></div><p class="muted">Backups include local user, release, file, announcement, website, and activity records. The password hash is not included.</p><div class="button-stack"><button class="button primary" data-action="export-backup">Download full backup</button><label class="button secondary file-button">Restore backup<input id="backupInput" type="file" accept=".json,application/json" hidden></label><button class="button quiet-danger" data-action="clear-data">Clear local records</button></div></section><section class="panel"><div class="panel-heading"><div><p class="eyebrow">ABOUT THIS INSTANCE</p><h2>Local operation</h2></div></div><div class="status-list"><div><span>Storage</span><b>IndexedDB <em>Ready</em></b></div><div><span>API connections</span><b>None <em>Disabled</em></b></div><div><span>Browser storage</span><b>${formatBytes(used)} <em>${blobs.length} files</em></b></div></div><p class="muted small">Data belongs to this browser origin. Clearing browser data removes it unless you restore a backup.</p></section></div>`;
    $('#backupInput').addEventListener('change', event => importBackup(event.target.files[0]).catch(showError));
  }

  async function renderStoreSettings() {
    setPage('Store settings', 'Manage store identity, currency, shipping, and payment options.');
    const store=await getState('store');
    $('#view').innerHTML=`<section class="panel" style="max-width:760px"><div class="panel-heading"><div><p class="eyebrow">STORE PROFILE</p><h2>Store information</h2></div><span class="panel-caption">Saved in this browser</span></div><form id="storeForm" class="form-grid"><label class="span-two">Website name<input name="name" maxlength="90" value="${escapeHtml(store.name)}" required></label><label>Currency<select name="currency">${['USD','CAD','AUD','GBP','EUR','INR','NZD','SGD'].map(currency=>`<option${store.currency===currency?' selected':''}>${currency}</option>`).join('')}</select></label><label class="span-two">Shipping information<textarea name="shippingInfo" rows="3" maxlength="700">${escapeHtml(store.shippingInfo)}</textarea></label><label class="span-two">Payment status options<input name="paymentStatuses" maxlength="180" value="${escapeHtml((store.paymentStatuses||[]).join(', '))}"><small>Comma-separated values used for new orders.</small></label><div class="dialog-actions span-two"><button class="button primary" type="submit">Save store settings</button></div></form><p class="security-warning">These settings and commerce records are local to this browser and do not publish to the hosted AURIX website.</p></section>`;
  }

  function showError(error) {
    console.error(error);
    toast(error?.message || String(error), 'error');
  }

  async function renderRoute() {
    const sequence = ++routeSequence;
    for (const url of temporaryObjectUrls) URL.revokeObjectURL(url);
    temporaryObjectUrls = [];
    const routes = {overview:renderOverview, products:renderProducts, orders:renderOrders, customers:renderCustomers, categories:renderCategories, coupons:renderCoupons, reports:renderReports, 'store-settings':renderStoreSettings, users:renderUsers, releases:renderReleases, files:renderFiles, announcements:renderAnnouncements, website:renderWebsite, activity:renderActivity, settings:renderSettings};
    routeName = location.hash.slice(1) || 'overview';
    if (!routes[routeName]) routeName = 'overview';
    document.querySelectorAll('[data-route]').forEach(button => button.classList.toggle('selected', button.dataset.route === routeName));
    const titles = {overview:'Overview',products:'Products',orders:'Orders',customers:'Customers',categories:'Categories',coupons:'Coupons',reports:'Reports & analytics','store-settings':'Store settings',users:'Users',releases:'Software & releases',files:'File library',announcements:'Announcements',website:'Website content',activity:'Activity log',settings:'Settings & backup'};

      async function saveProduct(form) {
        const data=new FormData(form),id=String(data.get('id')||''),products=await getState('products'),existing=products.find(item=>item.id===id);
        const name=String(data.get('name')||'').trim(),price=Number(data.get('price')),discountRaw=String(data.get('discountPrice')||''),discountPrice=discountRaw?Number(discountRaw):null,stock=Number(data.get('stock'));
        if(!name||!Number.isFinite(price)||price<0||!Number.isInteger(stock)||stock<0)throw new Error('Enter a product name, a valid price, and a non-negative whole stock quantity.');
        if(discountPrice!==null&&(!Number.isFinite(discountPrice)||discountPrice<0||discountPrice>=price))throw new Error('Discount price must be greater than or equal to zero and lower than the regular price.');
        const file=form.elements.image.files[0];if(file&&!file.type.startsWith('image/'))throw new Error('Choose an image file.');
        const productId=id||uid(),imageBlobId=file?`product:${productId}`:existing?.imageBlobId;
        if(file)await putBlob(imageBlobId,file);
        const product={id:productId,name,description:String(data.get('description')||'').trim(),price,discountPrice,stock,categoryId:String(data.get('categoryId')||''),featured:data.has('featured'),enabled:data.has('enabled'),imageBlobId,createdAt:existing?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()};
        if(existing)products[products.findIndex(item=>item.id===id)]=product;else products.unshift(product);
        await setState('products',products);await recordActivity(existing?'Product updated':'Product created',product.name);$('#recordDialog').close();toast('Product saved.','success');await renderProducts();
      }

      async function saveCustomer(form) {
        const data=new FormData(form),id=String(data.get('id')||''),customers=await getState('customers'),email=String(data.get('email')||'').trim().toLowerCase(),existing=customers.find(item=>item.id===id);
        if(customers.some(item=>item.email.toLowerCase()===email&&item.id!==id))throw new Error('A customer with this email already exists.');
        const customer={id:id||uid(),name:String(data.get('name')||'').trim(),email,phone:String(data.get('phone')||'').trim(),address:String(data.get('address')||'').trim(),createdAt:existing?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()};
        if(existing)customers[customers.findIndex(item=>item.id===id)]=customer;else customers.unshift(customer);
        await setState('customers',customers);await recordActivity(existing?'Customer updated':'Customer created',`${customer.name} · ${customer.email}`);$('#recordDialog').close();toast('Customer saved.','success');await renderCustomers();
      }

      async function saveCategory(form) {
        const data=new FormData(form),id=String(data.get('id')||''),categories=await getState('categories'),existing=categories.find(item=>item.id===id),name=String(data.get('name')||'').trim();
        if(categories.some(item=>item.name.toLowerCase()===name.toLowerCase()&&item.id!==id))throw new Error('A category with this name already exists.');
        const categoryId=id||uid(),file=form.elements.image.files[0],imageBlobId=file?`category:${categoryId}`:existing?.imageBlobId;
        if(file){if(!file.type.startsWith('image/'))throw new Error('Choose an image file.');await putBlob(imageBlobId,file);}
        const category={id:categoryId,name,description:String(data.get('description')||'').trim(),visible:data.has('visible'),imageBlobId,createdAt:existing?.createdAt||new Date().toISOString()};
        if(existing)categories[categories.findIndex(item=>item.id===id)]=category;else categories.unshift(category);
        await setState('categories',categories);await recordActivity(existing?'Category updated':'Category created',name);$('#recordDialog').close();toast('Category saved.','success');await renderCategories();
      }

      async function saveCoupon(form) {
        const data=new FormData(form),id=String(data.get('id')||''),coupons=await getState('coupons'),existing=coupons.find(item=>item.id===id),code=String(data.get('code')||'').trim().toUpperCase(),type=String(data.get('type')),value=Number(data.get('value')),minimumOrder=Number(data.get('minimumOrder')||0),usageLimit=String(data.get('usageLimit')||'');
        if(coupons.some(item=>item.code===code&&item.id!==id))throw new Error('That coupon code already exists.');
        if(!Number.isFinite(value)||value<=0||(type==='percent'&&value>100)||!Number.isFinite(minimumOrder)||minimumOrder<0)throw new Error('Enter a valid discount and minimum order amount.');
        if(usageLimit&&(!Number.isInteger(Number(usageLimit))||Number(usageLimit)<1))throw new Error('Usage limit must be a positive whole number.');
        const coupon={id:id||uid(),code,type,value,minimumOrder,expiresAt:String(data.get('expiresAt')||''),usageLimit:usageLimit?Number(usageLimit):null,enabled:data.has('enabled'),used:existing?.used||0,createdAt:existing?.createdAt||new Date().toISOString()};
        if(existing)coupons[coupons.findIndex(item=>item.id===id)]=coupon;else coupons.unshift(coupon);
        await setState('coupons',coupons);await recordActivity(existing?'Coupon updated':'Coupon created',code);$('#recordDialog').close();toast('Coupon saved.','success');await renderCoupons();
      }

      async function saveOrder(form) {
        const data=new FormData(form),[customers,products,orders]=await Promise.all([getState('customers'),getState('products'),getState('orders')]),customer=customers.find(item=>item.id===data.get('customerId')),product=products.find(item=>item.id===data.get('productId')),quantity=Number(data.get('quantity'));
        if(!customer||!product)throw new Error('Choose a valid customer and product.');
        if(!product.enabled||!Number.isInteger(quantity)||quantity<1||quantity>product.stock)throw new Error('Product is disabled or the requested quantity exceeds available stock.');
        const price=product.discountPrice!==null&&product.discountPrice!==undefined?Number(product.discountPrice):Number(product.price),order={id:uid(),number:String(Date.now()).slice(-8),customerId:customer.id,customerName:customer.name,customerEmail:customer.email,shippingAddress:String(data.get('shippingAddress')||'').trim(),items:[{productId:product.id,name:product.name,price,quantity}],total:price*quantity,paymentStatus:String(data.get('paymentStatus')),status:'Pending',createdAt:new Date().toISOString()};
        product.stock-=quantity;products[products.findIndex(item=>item.id===product.id)]=product;orders.unshift(order);
        await setManyState({products,orders});await recordActivity('Order created',`#${order.number} · ${customer.name} · ${formatMoney(order.total)}`);$('#recordDialog').close();toast('Order recorded.','success');await renderOrders();
      }

      async function setOrderStatus(order,status) {
        const [orders,products]=await Promise.all([getState('orders'),getState('products')]),current=orders.find(item=>item.id===order.id);
        if(!current)throw new Error('That order no longer exists.');
        if(status==='Cancelled'&&current.status!=='Cancelled')for(const line of current.items||[]){const product=products.find(item=>item.id===line.productId);if(product)product.stock+=Number(line.quantity)||0;}
        if(current.status==='Cancelled'&&status!=='Cancelled')for(const line of current.items||[]){const product=products.find(item=>item.id===line.productId);if(!product||product.stock<Number(line.quantity))throw new Error('Not enough stock to reopen this order.');product.stock-=Number(line.quantity)||0;}
        current.status=status;orders[orders.findIndex(item=>item.id===current.id)]=current;
        await setManyState({orders,products});await recordActivity('Order status changed',`#${current.number} · ${status}`);toast(`Order marked ${status.toLowerCase()}.`,'success');
      }

      async function saveStore(form) {
        const data=new FormData(form),paymentStatuses=[...new Set(String(data.get('paymentStatuses')||'').split(',').map(value=>value.trim()).filter(Boolean))];
        if(!paymentStatuses.length||paymentStatuses.some(value=>value.length>30))throw new Error('Add at least one payment status, each no longer than 30 characters.');
        await setState('store',{name:String(data.get('name')||'').trim(),currency:String(data.get('currency')),shippingInfo:String(data.get('shippingInfo')||'').trim(),paymentStatuses});
        await recordActivity('Store settings updated',String(data.get('name')));toast('Store settings saved.','success');await renderSettings();
      }
    commerceHandlers={saveProduct,saveCustomer,saveCategory,saveCoupon,saveOrder,setOrderStatus,saveStore};
    $('#pageTitle').textContent = titles[routeName];
    $('#view').innerHTML = '<div class="loading-state"><span class="loader"></span><span>Loading local records</span></div>';
    try {
      await routes[routeName]();
      if (sequence !== routeSequence) return;
    } catch (error) {
      if (sequence !== routeSequence) return;
      $('#view').innerHTML = `<section class="panel error-panel"><span class="state-chip negative">Storage error</span><h2>Could not load this section</h2><p>${escapeHtml(error.message || String(error))}</p><button class="button secondary" data-action="retry">Retry</button></section>`;
    }
  }

  async function saveUser(form) {
    const data = new FormData(form);
    const id = String(data.get('id') || '');
    const users = await getState('users');
    const email = String(data.get('email') || '').trim().toLowerCase();
    if (users.some(item => item.email.toLowerCase() === email && item.id !== id)) throw new Error('That email is already in the local directory.');
    const existing = users.find(item => item.id === id);
    const user = {id:id || uid(), name:String(data.get('name')).trim(), email, department:String(data.get('department') || '').trim(), role:String(data.get('role')), status:String(data.get('status')), notes:String(data.get('notes') || '').trim(), createdAt:existing?.createdAt || new Date().toISOString(), lastLoginAt:existing?.lastLoginAt || null};
    if (existing) users[users.findIndex(item => item.id === id)] = user;
    else users.unshift(user);
    await setState('users', users);
    await recordActivity(existing ? 'User updated' : 'User added', `${user.name} · ${user.email}`);
    $('#recordDialog').close();
    toast(existing ? 'User updated.' : 'User added.', 'success');
    await renderUsers();
  }

  async function saveRelease(form) {
    const data = new FormData(form);
    const id = String(data.get('id') || '');
    const releases = await getState('releases');
    const existing = releases.find(item => item.id === id);
    const file = form.elements.package.files[0];
    if (!existing && !file) throw new Error('Choose an EXE or ZIP package.');
    if (file && !/\.(exe|zip)$/i.test(file.name)) throw new Error('Release packages must be EXE or ZIP files.');
    const version = String(data.get('version') || '').trim();
    if (!/^\d+\.\d+(\.\d+)?$/.test(version)) throw new Error('Version must look like 1.0 or 1.0.0.');
    if (releases.some(item => item.version === version && item.platform === data.get('platform') && item.id !== id)) throw new Error('That version already exists for this platform.');
    const releaseId = id || uid();
    if (file) await putBlob(`release:${releaseId}`, file);
    const release = {
      id:releaseId, version, platform:String(data.get('platform')), fileName:file?.name || existing.fileName,
      fileSize:file?.size ?? existing.fileSize, fileType:file?.type || existing.fileType,
      blobId:file ? `release:${releaseId}` : existing.blobId, notes:String(data.get('notes') || '').trim(),
      minVersion:String(data.get('minVersion') || '').trim(), status:String(data.get('status')),
      downloads:existing?.downloads || 0, isLatest:existing?.isLatest || false,
      uploadedAt:existing?.uploadedAt || new Date().toISOString(), updatedAt:new Date().toISOString()
    };
    if (existing) releases[releases.findIndex(item => item.id === id)] = release;
    else releases.unshift(release);
    await setState('releases', releases);
    await recordActivity(existing ? 'Release updated' : 'Release added', `${release.version} · ${release.fileName}`);
    $('#recordDialog').close();
    toast('Release saved locally.', 'success');
    await renderReleases();
  }

  async function saveAnnouncement(form) {
    const data = new FormData(form);
    const id = String(data.get('id') || '');
    const items = await getState('announcements');
    const existing = items.find(item => item.id === id);
    const item = {id:id || uid(), title:String(data.get('title')).trim(), kind:String(data.get('kind')), status:String(data.get('status')), body:String(data.get('body')).trim(), createdAt:existing?.createdAt || new Date().toISOString(), updatedAt:new Date().toISOString()};
    if (existing) items[items.findIndex(value => value.id === id)] = item;
    else items.unshift(item);
    await setState('announcements', items);
    await recordActivity(existing ? 'Announcement updated' : 'Announcement created', item.title);
    $('#recordDialog').close();
    toast('Announcement saved.', 'success');
    await renderAnnouncements();
  }

  async function withBlob(id, filename, increment = null) {
    const saved = await getBlob(id);
    if (!saved?.blob) throw new Error('The file is missing from local browser storage.');
    const url = URL.createObjectURL(saved.blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename || saved.name || 'download';
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    if (increment) {
      const releases = await getState('releases');
      const release = releases.find(item => item.id === increment);
      if (release) {
        release.downloads = (release.downloads || 0) + 1;
        await setState('releases', releases);
        await recordActivity('Release downloaded', `${release.version} · ${release.fileName}`);
      }
    }
    return url;
  }

  async function copyReleaseLink(release) {
    const saved = await getBlob(release.blobId);
    if (!saved?.blob) throw new Error('The release file is missing.');
    if (temporaryObjectUrl) URL.revokeObjectURL(temporaryObjectUrl);
    temporaryObjectUrl = URL.createObjectURL(saved.blob);
    await navigator.clipboard.writeText(temporaryObjectUrl);
    toast('Temporary link copied. It works only in this browser session.', 'success');
  }

  function triggerDownload(filename, content, type = 'application/json') {
    const blob = content instanceof Blob ? content : new Blob([content], {type});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error || new Error('Could not read a stored file for backup.'));
      reader.readAsDataURL(blob);
    });
  }

  function dataUrlToBlob(dataUrl) {
    const [header, data] = dataUrl.split(',');
    const type = header.match(/data:([^;]+)/)?.[1] || 'application/octet-stream';
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new Blob([bytes], {type});
  }

  async function exportBackup() {
    const data = {};
    for (const key of STATE_KEYS) data[key] = await getState(key);
    const blobs = await allBlobs();
    data.blobs = await Promise.all(blobs.map(async item => ({id:item.id, name:item.name, type:item.type, size:item.size, modified:item.modified, data:await blobToDataUrl(item.blob)})));
    data.format = 'aurix-local-admin-backup';
    data.version = 1;
    data.exportedAt = new Date().toISOString();
    triggerDownload(`aurix-admin-backup-${dayKey(new Date())}.json`, JSON.stringify(data));
    await recordActivity('Backup exported', `${blobs.length} files · ${formatBytes(blobs.reduce((sum, item) => sum + (item.size || 0), 0))}`);
    toast('Local backup downloaded.', 'success');
  }

  async function exportWebsite() {
    const website = await getState('website');
    triggerDownload('aurix-website-content.json', JSON.stringify({format:'aurix-website-content', version:1, content:website}, null, 2));
    await recordActivity('Website content exported', 'Homepage fields');
  }

  async function importBackup(file) {
    if (!file) return;
    const data = JSON.parse(await file.text());
    if (data.format !== 'aurix-local-admin-backup' || data.version !== 1) throw new Error('This file is not a supported AURIX local backup.');
    for (const key of STATE_KEYS) if (data[key] === undefined && !['products','orders','customers','categories','coupons','store'].includes(key)) throw new Error(`Backup is missing the ${key} dataset.`);
    if (!await confirmAction('Restore local backup?', 'This replaces all current local records and files. Your admin password stays unchanged.')) return;
    const tx = database.transaction('blobs', 'readwrite');
    tx.objectStore('blobs').clear();
    for (const item of data.blobs || []) tx.objectStore('blobs').put({id:item.id, name:item.name, type:item.type, size:item.size, modified:item.modified, blob:dataUrlToBlob(item.data)});
    await new Promise((resolve, reject) => {tx.oncomplete = resolve; tx.onerror = () => reject(tx.error || new Error('Could not restore file data.'));});
    const values = Object.fromEntries(STATE_KEYS.map(key => [key, data[key] ?? structuredClone(DEFAULTS[key])]));
    await setManyState(values);
    await recordActivity('Backup restored', file.name);
    toast('Backup restored.', 'success');
    await renderSettings();
  }

  async function exportActivity() {
    const items = await getState('activities');
    const rows = [['Time','Action','Details'], ...items.map(item => [item.at, item.action, item.detail])];
    const csv = rows.map(row => row.map(value => `"${String(value ?? '').replaceAll('"','""')}"`).join(',')).join('\r\n');
    triggerDownload('aurix-activity.csv', csv, 'text/csv');
  }

  async function exportReport() {
    const [orders,store]=await Promise.all([getState('orders'),getState('store')]);
    const rows=[['Order','Date','Customer','Email','Status','Payment status','Products','Quantity','Total','Currency']];
    for(const order of orders)for(const item of order.items||[])rows.push([order.number,order.createdAt,order.customerName,order.customerEmail,order.status,order.paymentStatus,item.name,item.quantity,Number(item.price)*Number(item.quantity),store.currency]);
    const csv=rows.map(row=>row.map(value=>`"${String(value??'').replaceAll('"','""')}"`).join(',')).join('\r\n');
    triggerDownload(`aurix-sales-report-${dayKey(new Date())}.csv`,csv,'text/csv');
    await recordActivity('Sales report exported',`${orders.length} orders`);
  }

  async function changePassword() {
    const auth = readAuth();
    $('#modalContent').innerHTML = `<div class="dialog-head"><div><p class="eyebrow">LOCAL SECURITY</p><h2>Change password</h2></div><button class="icon-button" data-action="close-modal" aria-label="Close">×</button></div><form id="passwordForm" class="form-stack"><label>Current password<input name="current" type="password" autocomplete="current-password" required></label><label>New password<input name="next" type="password" minlength="10" autocomplete="new-password" required><small>At least 10 characters.</small></label><label>Confirm new password<input name="confirm" type="password" minlength="10" autocomplete="new-password" required></label><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Update password</button></div></form>`;
    $('#recordDialog').showModal();
    $('#passwordForm').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = new FormData(form);
      const currentHash = await passwordHash(String(data.get('current')), hexToBytes(auth.salt));
      if (currentHash !== auth.hash) throw new Error('Current password is incorrect.');
      const next = String(data.get('next'));
      if (next.length < 10) throw new Error('Choose a password with at least 10 characters.');
      if (next !== String(data.get('confirm'))) throw new Error('The new passwords do not match.');
      const salt = crypto.getRandomValues(new Uint8Array(16));
      auth.salt = bytesToHex(salt);
      auth.hash = await passwordHash(next, salt);
      localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
      $('#recordDialog').close();
      toast('Local password updated.', 'success');
    });
  }

  async function clearLocalData() {
    if (!await confirmAction('Clear local records?', 'This permanently deletes users, releases, files, announcements, website content, activities, and sign-in history from this browser. Your admin lock remains.')) return;
    await new Promise((resolve, reject) => {
      const tx = database.transaction(['state','blobs'], 'readwrite');
      tx.objectStore('state').clear(); tx.objectStore('blobs').clear();
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error || new Error('Could not clear local records.'));
    });
    await setManyState(DEFAULTS);
    await recordActivity('Local records cleared', 'Admin lock retained');
    toast('Local records cleared.', 'success');
    await renderSettings();
  }

  async function handleAction(button) {
    const action = button.dataset.action;
    const id = button.dataset.id;
    if (action === 'close-modal') { $('#recordDialog').close(); return; }
    if (action === 'retry') { await renderRoute(); return; }
    if (action === 'logout') { logout(); return; }
    if (action === 'export-backup') { await exportBackup(); return; }
    if (action === 'export-website') { await exportWebsite(); return; }
    if (action === 'export-activity') { await exportActivity(); return; }
    if (action === 'export-report') { await exportReport(); return; }
    if (action === 'change-password') { await changePassword(); return; }
    if (action === 'clear-data') { await clearLocalData(); return; }
    if (action === 'clear-activity') {
      if (!await confirmAction('Clear activity log?', 'This removes the local audit trail.')) return;
      await setState('activities', []); await renderActivity(); toast('Activity log cleared.'); return;
    }
    if (action === 'choose-files') { $('#filesInput').click(); return; }
    if (action === 'new-user') { openUserForm(); return; }
    if (action === 'new-release') { openReleaseForm(); return; }
    if (action === 'new-announcement') { openAnnouncementForm(); return; }
    if (action === 'new-product') { await openProductForm(); return; }
    if (action === 'new-order') { await openOrderForm(); return; }
    if (action === 'new-customer') { openCustomerForm(); return; }
    if (action === 'new-category') { openCategoryForm(); return; }
    if (action === 'new-coupon') { openCouponForm(); return; }
    if (action === 'view-order' || action === 'cancel-order') {
      const orders=await getState('orders'),order=orders.find(item=>item.id===id);
      if(!order)throw new Error('That order no longer exists.');
      if(action==='view-order'){const store=await getState('store');showOrder(order,store.currency);}
      if(action==='cancel-order'&&await confirmAction('Cancel order?',`Cancel order #${order.number}? The items will return to stock.`)){await commerceHandlers.setOrderStatus(order,'Cancelled');$('#recordDialog').close();await renderOrders();}
      return;
    }
    if (action === 'edit-product' || action === 'delete-product') {
      const products=await getState('products'),product=products.find(item=>item.id===id);
      if(!product)throw new Error('That product no longer exists.');
      if(action==='edit-product')await openProductForm(product);
      if(action==='delete-product'&&await confirmAction('Delete product?',`Remove ${product.name} from the catalog? Existing order history is preserved.`)){if(product.imageBlobId)await removeBlob(product.imageBlobId);await setState('products',products.filter(item=>item.id!==id));await recordActivity('Product deleted',product.name);await renderProducts();toast('Product deleted.','success');}
      return;
    }
    if (action === 'view-customer' || action === 'edit-customer' || action === 'delete-customer') {
      const customers=await getState('customers'),customer=customers.find(item=>item.id===id);
      if(!customer)throw new Error('That customer no longer exists.');
      if(action==='view-customer')await showCustomer(customer);
      if(action==='edit-customer')openCustomerForm(customer);
      if(action==='delete-customer'){
        const orders=await getState('orders');
        if(orders.some(order=>order.customerId===id))throw new Error('This customer has order history and cannot be deleted.');
        if(await confirmAction('Delete customer?',`Remove ${customer.name} (${customer.email})?`)){await setState('customers',customers.filter(item=>item.id!==id));await recordActivity('Customer deleted',customer.email);await renderCustomers();toast('Customer deleted.','success');}
      }
      return;
    }
    if (action === 'edit-category' || action === 'toggle-category' || action === 'delete-category') {
      const categories=await getState('categories'),category=categories.find(item=>item.id===id);
      if(!category)throw new Error('That category no longer exists.');
      if(action==='edit-category')openCategoryForm(category);
      if(action==='toggle-category'){category.visible=!category.visible;await setState('categories',categories);await recordActivity('Category visibility changed',`${category.name} · ${category.visible?'visible':'hidden'}`);await renderCategories();}
      if(action==='delete-category'){
        const products=await getState('products');
        if(products.some(product=>product.categoryId===id))throw new Error('Move or edit this category’s products before deleting it.');
        if(await confirmAction('Delete category?',`Remove ${category.name}?`)){if(category.imageBlobId)await removeBlob(category.imageBlobId);await setState('categories',categories.filter(item=>item.id!==id));await recordActivity('Category deleted',category.name);await renderCategories();}
      }
      return;
    }
    if (action === 'edit-coupon' || action === 'toggle-coupon' || action === 'delete-coupon') {
      const coupons=await getState('coupons'),coupon=coupons.find(item=>item.id===id);
      if(!coupon)throw new Error('That coupon no longer exists.');
      if(action==='edit-coupon')openCouponForm(coupon);
      if(action==='toggle-coupon'){coupon.enabled=!coupon.enabled;await setState('coupons',coupons);await recordActivity('Coupon status changed',`${coupon.code} · ${coupon.enabled?'enabled':'disabled'}`);await renderCoupons();}
      if(action==='delete-coupon'&&await confirmAction('Delete coupon?',`Remove ${coupon.code}?`)){await setState('coupons',coupons.filter(item=>item.id!==id));await recordActivity('Coupon deleted',coupon.code);await renderCoupons();}
      return;
    }
    if (action === 'view-user' || action === 'edit-user' || action === 'toggle-user' || action === 'delete-user') {
      const users = await getState('users');
      const user = users.find(item => item.id === id);
      if (!user) throw new Error('That user no longer exists.');
      if (action === 'view-user') showUserProfile(user);
      if (action === 'edit-user') openUserForm(user);
      if (action === 'toggle-user') {
        user.status = user.status === 'active' ? 'inactive' : 'active';
        await setState('users', users); await recordActivity('User status changed', `${user.email} · ${user.status}`); await renderUsers();
      }
      if (action === 'delete-user' && await confirmAction('Delete user?', `Remove ${user.name} (${user.email}) from this local directory?`)) {
        await setState('users', users.filter(item => item.id !== id)); await recordActivity('User deleted', user.email); await renderUsers();
      }
      return;
    }
    if (action === 'edit-release' || action === 'download-release' || action === 'copy-release-link' || action === 'delete-release' || action === 'toggle-release' || action === 'latest-release') {
      const releases = await getState('releases');
      const release = releases.find(item => item.id === id);
      if (!release) throw new Error('That release no longer exists.');
      if (action === 'edit-release') openReleaseForm(release);
      if (action === 'download-release') await withBlob(release.blobId, release.fileName, release.id);
      if (action === 'copy-release-link') await copyReleaseLink(release);
      if (action === 'toggle-release') {
        release.status = release.status === 'published' ? 'draft' : 'published';
        await setState('releases', releases); await recordActivity('Release publication changed', `${release.version} · ${release.status}`); await renderReleases();
      }
      if (action === 'latest-release') {
        for (const item of releases) if (item.platform === release.platform) item.isLatest = item.id === id;
        await setState('releases', releases); await recordActivity('Latest release changed', `${release.version} · ${release.platform}`); await renderReleases();
      }
      if (action === 'delete-release' && await confirmAction('Delete release?', `Remove ${release.version} and its local package file?`)) {
        await removeBlob(release.blobId); await setState('releases', releases.filter(item => item.id !== id)); await recordActivity('Release deleted', `${release.version} · ${release.fileName}`); await renderReleases();
      }
      return;
    }
    if (action === 'preview-file' || action === 'download-file' || action === 'delete-file') {
      const files = await getState('files');
      const file = files.find(item => item.id === id);
      if (!file) throw new Error('That file no longer exists.');
      if (action === 'preview-file') await previewFile(file);
      if (action === 'download-file') await withBlob(file.id, file.name);
      if (action === 'delete-file' && await confirmAction('Delete file?', `Remove ${file.name} and its local copy?`)) {
        await removeBlob(file.id); await setState('files', files.filter(item => item.id !== id)); await recordActivity('File deleted', file.name); await renderFiles();
      }
      return;
    }
    if (action === 'edit-announcement' || action === 'toggle-announcement' || action === 'delete-announcement') {
      const items = await getState('announcements');
      const item = items.find(record => record.id === id);
      if (!item) throw new Error('That announcement no longer exists.');
      if (action === 'edit-announcement') openAnnouncementForm(item);
      if (action === 'toggle-announcement') { item.status = item.status === 'published' ? 'draft' : 'published'; await setState('announcements', items); await recordActivity('Announcement publication changed', `${item.title} · ${item.status}`); await renderAnnouncements(); }
      if (action === 'delete-announcement' && await confirmAction('Delete announcement?', `Remove “${item.title}” from this local dashboard?`)) { await setState('announcements', items.filter(record => record.id !== id)); await recordActivity('Announcement deleted', item.title); await renderAnnouncements(); }
    }
  }

  async function submitForm(form) {
    if (form.id === 'userForm') await saveUser(form);
    if (form.id === 'releaseForm') await saveRelease(form);
    if (form.id === 'announcementForm') await saveAnnouncement(form);
    if (form.id === 'productForm') await commerceHandlers.saveProduct(form);
    if (form.id === 'customerForm') await commerceHandlers.saveCustomer(form);
    if (form.id === 'categoryForm') await commerceHandlers.saveCategory(form);
    if (form.id === 'couponForm') await commerceHandlers.saveCoupon(form);
    if (form.id === 'orderForm') await commerceHandlers.saveOrder(form);
    if (form.id === 'storeForm') await commerceHandlers.saveStore(form);
  }

  function showAppError(error) {
    console.error(error);
    $('#authView').classList.remove('hidden');
    $('#appShell').classList.add('hidden');
    $('#authView').innerHTML = `<section class="auth-panel"><div class="brand-mark">A</div><p class="eyebrow">AURIX / STORAGE ERROR</p><h1>Local storage unavailable<span class="accent">.</span></h1><p class="muted">${escapeHtml(error.message || String(error))}</p><p class="security-copy">Start the dashboard with <b>run_admin.py</b> from the project folder, then open the localhost address it prints.</p></section>`;
  }

  async function init() {
    $('#nav').innerHTML = navMarkup();
    $('#authView').addEventListener('submit', async event => {
      if (!['setupForm','loginForm'].includes(event.target.id)) return;
      event.preventDefault();
      const button = $('button[type="submit"]', event.target);
      button.disabled = true;
      try {
        if (event.target.id === 'setupForm') await setupAdmin(event.target);
        else await loginAdmin(event.target);
      } catch (error) { toast(error.message || String(error), 'error'); }
      finally { if (button.isConnected) button.disabled = false; }
    });
    $('#nav').addEventListener('click', event => {
      const button = event.target.closest('[data-route]');
      if (!button) return;
      location.hash = button.dataset.route;
      $('#sideNav').classList.remove('nav-open');
    });
    $('#pageAction').addEventListener('click', event => {
      const button = event.target.closest('[data-action]');
      if (button) handleAction(button).catch(showError);
    });
    $('#view').addEventListener('click', event => {
      const routeButton = event.target.closest('[data-route]');
      if (routeButton) { location.hash = routeButton.dataset.route; return; }
      const button = event.target.closest('[data-action]');
      if (button) handleAction(button).catch(showError);
    });
    $('#view').addEventListener('change', event => {
      const control = event.target.closest('[data-action="order-status"]');
      if (!control) return;
      const ordersPromise=getState('orders');
      ordersPromise.then(orders=>{
        const order=orders.find(item=>item.id===control.dataset.id);
        if(!order)throw new Error('That order no longer exists.');
        return commerceHandlers.setOrderStatus(order,control.value).then(renderOrders);
      }).catch(showError);
    });
    $('#modalContent').addEventListener('click', event => {
      const button = event.target.closest('[data-action]');
      if (button) handleAction(button).catch(showError);
    });
    $('#modalContent').addEventListener('submit', event => {
      event.preventDefault();
      submitForm(event.target).catch(showError);
    });
    $('#logoutButton').addEventListener('click', logout);
    $('#menuButton').addEventListener('click', () => $('#sideNav').classList.toggle('nav-open'));
    $('#recordDialog').addEventListener('close', () => {
      if (temporaryObjectUrl) { URL.revokeObjectURL(temporaryObjectUrl); temporaryObjectUrl = null; }
      $('#modalContent').innerHTML = '';
    });
    window.addEventListener('hashchange', renderRoute);
    for (const event of ['pointerdown','keydown','touchstart']) window.addEventListener(event, touchSession, {passive:true});
    window.setInterval(() => {
      if (!readSession() && !$('#appShell').classList.contains('hidden')) logout();
    }, 15000);
    try {
      database = await openDatabase();
      const session = readSession();
      if (session && readAuth()) launchApp(); else showAuth();
    } catch (error) { showAppError(error); }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
