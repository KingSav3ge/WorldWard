/* WorldWard in a claude.ai artifact.
 * Starts Python (Pyodide) in this page, runs the unchanged WorldWard host and
 * Engine inside it, and answers the interface's /api/ requests in-process.
 * Saves are mirrored to this viewer's private claude.ai storage when
 * available, otherwise to this browser's storage.
 */
(function () {
  'use strict';
  const CONFIG = JSON.parse(document.getElementById('ww-config').textContent);
  const $ = (id) => document.getElementById(id);
  const realFetch = window.fetch.bind(window);
  let resolveReady, rejectReady;
  const ready = new Promise((a, b) => { resolveReady = a; rejectReady = b; });
  let py = null, bridge = null, storage = null, lastSnapshot = {};
  let promising = typeof WebAssembly !== 'undefined' && typeof WebAssembly.Suspending === 'function';
  let chain = Promise.resolve();
  const serial = (task) => { const next = chain.then(task, task); chain = next.catch(() => {}); return next; };

  function status(text) { const el = $('ww-boot-status'); if (el) el.textContent = text; }
  function fail(message, detail) {
    const box = $('ww-boot');
    if (!box) return;
    box.dataset.state = 'error';
    status(message);
    const more = $('ww-boot-detail');
    if (more && detail) { more.textContent = String(detail).slice(0, 600); more.hidden = false; }
  }
  function saveState(state, text) {
    const pill = $('ww-save'); if (!pill) return;
    pill.dataset.state = state; pill.textContent = text; pill.hidden = false;
  }

  // Archives are published as base64 text (artifacts serve no .zip files).
  // Requests for the original names, from this page or from Pyodide, are
  // answered by decoding the published .txt copy.
  const TEXT_ENCODED = ['worldward.zip', 'python_stdlib.zip', CONFIG.sqliteWheel];
  async function decodedFetch(url) {
    const response = await realFetch(url.split('?')[0] + '.txt');
    if (!response.ok) return response;
    const bytes = fromB64((await response.text()).replace(/\s+/g, ''));
    return new Response(bytes, { status: 200, headers: { 'Content-Type': 'application/octet-stream' } });
  }

  // ---- interface requests -> in-page host ----------------------------------
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : (input && input.url) || '';
    let pathname = '';
    try { pathname = new URL(url, location.href).pathname; } catch (e) { pathname = url; }
    if (TEXT_ENCODED.some((name) => pathname.endsWith('/' + name))) return decodedFetch(url);
    if (!url.startsWith('/api/')) return realFetch(input, init);
    await ready;
    init = init || {};
    const method = (init.method || 'GET').toUpperCase();
    const headers = {};
    new Headers(init.headers || {}).forEach((value, key) => { headers[key] = value; });
    const body = typeof init.body === 'string' ? new TextEncoder().encode(init.body) : null;
    const reply = await serial(async () => {
      let result;
      if (promising) {
        try { result = await bridge.dispatch.callPromising(method, url, JSON.stringify(headers), body); }
        catch (error) {
          if (!/stack switching|JSPI|callPromising/i.test(String(error))) throw error;
          promising = false;  // This browser cannot suspend Python; assistance stays off.
        }
      }
      if (!promising) result = bridge.dispatch(method, url, JSON.stringify(headers), body);
      const [code, type, payload] = result.toJs();
      result.destroy();
      if (method !== 'GET') await persist();
      return { code, type, payload };
    });
    return new Response(reply.payload, { status: reply.code, headers: { 'Content-Type': reply.type } });
  };

  // ---- save storage ----------------------------------------------------------
  const CHUNK = 150000;  // raw bytes per stored part (base64 stays under 256 KiB)
  const toB64 = (bytes) => { let s = ''; for (let i = 0; i < bytes.length; i += 32768) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768)); return btoa(s); };
  const fromB64 = (text) => { const s = atob(text); const out = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i); return out; };
  async function sha(text) { const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)); return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join(''); }

  async function claudeStorage() {
    if (!window.claude || typeof window.claude.use !== 'function') return null;
    const [db, user] = await Promise.all([window.claude.use('db'), window.claude.use('user')]);
    if (!db || !user) return null;
    const uid = await user.id();
    if (!uid) return null;
    const base = 'data/users/' + uid;
    const manifestRef = db.doc(base + '/worldward-saves');
    return {
      label: 'your Claude account',
      async load() {
        const snap = await manifestRef.get();
        if (!snap.exists) return {};
        const files = snap.data().files || {};
        const out = {};
        for (const [path, entry] of Object.entries(files)) {
          const parts = await Promise.all(entry.parts.map((id) => db.doc(base + '/' + id).get()));
          const text = parts.map((p) => (p.exists ? p.data().data : '')).join('');
          out[path] = { bytes: fromB64(text), sha: entry.sha };
        }
        return out;
      },
      async save(changed, removed, all) {
        const snap = await manifestRef.get();
        const files = snap.exists ? (snap.data().files || {}) : {};
        const stale = [];
        for (const [path, entry] of Object.entries(changed)) {
          const text = toB64(entry.bytes), key = (await sha(path)).slice(0, 20), parts = [];
          for (let i = 0, n = 0; i < Math.max(text.length, 1); i += CHUNK * 4 / 3, n++) {
            const id = 'ww-' + key + '-' + entry.sha.slice(0, 16) + '-' + n;
            await db.doc(base + '/' + id).set({ path, part: n, data: text.slice(i, i + CHUNK * 4 / 3) });
            parts.push(id);
          }
          if (files[path]) stale.push(...files[path].parts.filter((id) => !parts.includes(id)));
          files[path] = { sha: entry.sha, parts };
        }
        for (const path of removed) { if (files[path]) { stale.push(...files[path].parts); delete files[path]; } }
        await manifestRef.set({ version: 1, files, updated: new Date().toISOString() });
        for (const id of stale) { try { await db.doc(base + '/' + id).delete(); } catch (e) { /* left as unused part */ } }
      }
    };
  }

  function browserStorage() {
    const open = () => new Promise((resolve, reject) => {
      const request = indexedDB.open('worldward-saves', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('files');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const tx = async (mode, work) => { const db = await open(); return new Promise((resolve, reject) => {
      const t = db.transaction('files', mode), store = t.objectStore('files'); const out = work(store);
      t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out); t.onerror = () => reject(t.error); }); };
    return {
      label: 'this browser only',
      async load() {
        const db = await open();
        return new Promise((resolve, reject) => {
          const out = {}, t = db.transaction('files', 'readonly'), cursor = t.objectStore('files').openCursor();
          cursor.onsuccess = () => { const c = cursor.result; if (c) { out[c.key] = c.value; c.continue(); } };
          t.oncomplete = () => resolve(out); t.onerror = () => reject(t.error);
        });
      },
      async save(changed, removed) {
        await tx('readwrite', (store) => {
          for (const [path, entry] of Object.entries(changed)) store.put({ bytes: entry.bytes, sha: entry.sha }, path);
          for (const path of removed) store.delete(path);
        });
      }
    };
  }

  async function persist() {
    if (!storage) return;
    const now = JSON.parse(bridge.snapshot());
    const changed = {}, removed = [];
    for (const [path, digest] of Object.entries(now)) {
      if (lastSnapshot[path] !== digest) changed[path] = { sha: digest, bytes: py.FS.readFile(path) };
    }
    for (const path of Object.keys(lastSnapshot)) if (!(path in now)) removed.push(path);
    if (!Object.keys(changed).length && !removed.length) return;
    saveState('saving', 'Saving…');
    try {
      await storage.save(changed, removed, now);
      lastSnapshot = now;
      saveState('saved', 'Saved to ' + storage.label);
    } catch (error) {
      saveState('error', 'Not saved. Your last change stays in this page until it closes. ' + (error.code || ''));
    }
  }

  // ---- start -------------------------------------------------------------------
  async function start() {
    try {
      status('Loading Python…');
      py = await loadPyodide({ indexURL: CONFIG.pyodideIndex });
      status('Loading WorldWard…');
      await py.loadPackage(CONFIG.pyodideIndex + CONFIG.sqliteWheel);
      const zip = await decodedFetch(CONFIG.bundle);
      if (!zip.ok) throw new Error('The WorldWard bundle could not be loaded (' + zip.status + ').');
      const bytes = new Uint8Array(await zip.arrayBuffer());
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (b) => b.toString(16).padStart(2, '0')).join('');
      if (digest !== CONFIG.bundleSha256) throw new Error('The WorldWard bundle does not match this page.');
      py.unpackArchive(bytes, 'zip', { extractDir: '/worldward' });
      py.FS.writeFile('/worldward/bridge.py', document.getElementById('ww-bridge').textContent);
      py.FS.writeFile('/worldward/claude_assist.py', document.getElementById('ww-assist').textContent);
      py.runPython("import sys; sys.path.insert(0, '/worldward')");
      bridge = py.pyimport('bridge');
      bridge.verify_bundle();
      status('Opening your saves…');
      try { storage = (await claudeStorage()) || browserStorage(); } catch (e) { storage = browserStorage(); }
      try {
        const files = await storage.load();
        for (const [path, entry] of Object.entries(files)) bridge.restore(path, entry.bytes);
      } catch (error) {
        storage = null;
        saveState('error', 'Saved games could not be opened, so saving is off for this visit.');
      }
      const assist = py.pyimport('claude_assist');
      let sample = null;
      try { sample = window.claude && typeof window.claude.use === 'function' ? await window.claude.use('sample') : null; } catch (e) { sample = null; }
      // Claude answers asynchronously; Python waits for it through stack switching (JSPI).
      const ask = sample && promising ? (prompt) => sample.json(prompt, { modelTier: 'quick', cache: false })
        .then((value) => JSON.stringify({ ok: true, value }), (error) => JSON.stringify({ ok: false, code: (error && error.code) || 'upstream_error' })) : null;
      const configuration = assist.configure(ask, promising);
      bridge.start(configuration);
      window.__worldward.assistance = configuration ? 'claude' : (sample ? 'needs-newer-browser' : 'off');
      lastSnapshot = JSON.parse(bridge.snapshot());
      if (storage) saveState('saved', 'Saves: ' + storage.label);
      resolveReady();
      $('ww-boot').hidden = true;
    } catch (error) {
      rejectReady(error);
      fail('WorldWard could not start in this page.', error && (error.message || error));
    }
  }
  window.__worldward = { ready, persist };
  // Pyodide's scripts load after this one; start once the page has parsed.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
