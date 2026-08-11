"""
Mini tableau de bord statique, zéro dépendance (pas de Node/npm/Docker
nécessaire) -- pensé pour quelqu'un qui n'a rien d'autre que Python déjà
installé. Chaque page ici est du HTML/CSS/JS pur, servi directement par
FastAPI, qui va chercher ses données via les mêmes endpoints JSON que le
vrai frontend Next.js (frontend/) -- donc tout ce qui est affiché ici est
réel, jamais inventé.

Le vrai frontend (frontend/) reste la version complète/recommandée une fois
Node.js ou Docker disponibles ; ceci est le filet de sécurité qui marche
partout, tout de suite.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["demo"])

NAV = [
    ("/demo", "Dashboard"),
    ("/demo/accounts", "Comptes"),
    ("/demo/masters", "Masters"),
    ("/demo/inventory", "Inventaire"),
    ("/demo/calendar", "Calendrier"),
    ("/demo/queue", "Queue"),
    ("/demo/errors", "Erreurs"),
]

_STYLE = """
body { font-family: -apple-system, Segoe UI, sans-serif; background: #0b0f14; color: #e6edf3; margin: 0; }
.wrap { max-width: 1000px; margin: 0 auto; padding: 1.5rem 2rem 3rem; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 0.75rem; }
h1 { font-size: 1.2rem; margin: 0; }
nav { display: flex; gap: 1rem; flex-wrap: wrap; }
nav a { color: #8b98a5; text-decoration: none; font-size: 0.9rem; padding: 0.25rem 0; }
nav a.active { color: #fff; border-bottom: 2px solid #58a6ff; }
nav a:hover { color: #fff; }
.banner { background: #3d2e0a; border: 1px solid #7a5c14; color: #f0c674; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; font-size: 0.85rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 1rem; }
.card .label { color: #8b98a5; font-size: 0.72rem; text-transform: uppercase; }
.card .value { font-size: 1.6rem; font-weight: 600; margin-top: 0.3rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }
th { text-align: left; background: #0d1117; color: #8b98a5; text-transform: uppercase; font-size: 0.7rem; padding: 0.6rem 0.9rem; }
td { padding: 0.6rem 0.9rem; border-top: 1px solid #21262d; }
tr:hover td { background: #1c2128; }
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.72rem; border: 1px solid #30363d; background: #21262d; }
.badge-ok { background: #0d2818; color: #56d364; border-color: #1b5c33; }
.badge-warn { background: #2b2111; color: #e3b341; border-color: #5c4813; }
.badge-bad { background: #2c1215; color: #f85149; border-color: #6e2528; }
.empty { text-align: center; color: #8b98a5; padding: 2.5rem; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }
button, .btn { background: #21262d; color: #e6edf3; border: 1px solid #30363d; padding: 0.5rem 0.9rem; border-radius: 6px; font-size: 0.82rem; cursor: pointer; }
button.primary { background: #238636; border-color: #2ea043; }
button.warn { background: #9e6a03; border-color: #bb8009; }
button:hover { filter: brightness(1.15); }
.actions { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.muted { color: #8b98a5; }
"""


def _shell(active_path: str, title: str, body: str) -> str:
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if href == active_path else ""}">{label}</a>' for href, label in NAV
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Instagram Content Factory — {title}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📦 Instagram Content Factory</h1>
    <nav>{nav_html}</nav>
  </header>
  {body}
</div>
</body>
</html>"""


def _page(active_path: str, title: str, body: str) -> HTMLResponse:
    return HTMLResponse(_shell(active_path, title, body))


@router.get("/demo", response_class=HTMLResponse)
def demo_dashboard():
    body = """
    <div class="banner">⚠️ Aperçu sans dépendance (pas de Docker/Node nécessaire). Les chiffres viennent de la vraie base de données.</div>
    <div id="grid" class="grid">Chargement...</div>
    <script>
    fetch('/dashboard/summary').then(r => r.json()).then(d => {
      const v = d.variants_by_status || {};
      const cards = [
        ['Comptes connectés', d.accounts_total], ['Comptes actifs', d.accounts_active],
        ['Masters', d.masters_total], ['Variantes disponibles', v.AVAILABLE || 0],
        ['Variantes publiées', v.PUBLISHED || 0], ['Captions manquantes', d.missing_captions],
        ['Mode DRY RUN', d.dry_run ? 'Oui (sécurisé)' : 'Non'],
      ];
      document.getElementById('grid').innerHTML = cards.map(([l, v]) =>
        `<div class="card"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');
    }).catch(e => document.getElementById('grid').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    </script>
    """
    return _page("/demo", "Dashboard", body)


@router.get("/demo/accounts", response_class=HTMLResponse)
def demo_accounts():
    body = """
    <div id="content">Chargement...</div>
    <script>
    fetch('/accounts?limit=500').then(r => r.json()).then(rows => {
      if (!rows.length) { document.getElementById('content').innerHTML = '<div class="empty">Aucun compte pour l\\'instant.</div>'; return; }
      const badge = s => `<span class="badge">${s}</span>`;
      document.getElementById('content').innerHTML = `<table><thead><tr>
        <th>Username</th><th>Fuseau horaire</th><th>Statut</th><th>Connexion</th><th>Posts/jour</th>
        </tr></thead><tbody>` + rows.map(a => `<tr>
          <td>${a.username}</td><td class="muted">${a.timezone}</td>
          <td>${badge(a.status)}</td><td>${badge(a.connection_status)}</td>
          <td class="muted">${a.daily_min_posts}–${a.daily_max_posts}</td>
        </tr>`).join('') + `</tbody></table>`;
    }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    </script>
    """
    return _page("/demo/accounts", "Comptes", body)


@router.get("/demo/masters", response_class=HTMLResponse)
def demo_masters():
    body = """
    <div class="actions">
      <label class="btn" style="display:inline-block">
        📤 Envoyer une vidéo
        <input type="file" id="fileInput" accept="video/mp4,video/quicktime" style="display:none" onchange="uploadFile()">
      </label>
      <span id="uploadStatus" class="muted"></span>
    </div>
    <div id="content">Chargement...</div>
    <script>
    function uploadFile() {
      const input = document.getElementById('fileInput');
      const status = document.getElementById('uploadStatus');
      if (!input.files.length) return;
      const formData = new FormData();
      formData.append('file', input.files[0]);
      status.textContent = 'Envoi en cours...';
      fetch('/masters/upload', {method: 'POST', body: formData})
        .then(r => r.json())
        .then(d => { status.textContent = d.status + ' -- ' + d.variants_created + ' variantes créées'; load(); })
        .catch(e => { status.textContent = 'Erreur : ' + e; });
    }
    function load() {
      fetch('/masters?limit=500').then(r => r.json()).then(rows => {
        if (!rows.length) { document.getElementById('content').innerHTML = '<div class="empty">Aucun master pour l\\'instant. Envoie une vidéo avec le bouton ci-dessus.</div>'; return; }
        document.getElementById('content').innerHTML = `<table><thead><tr>
          <th>Master</th><th>Créé</th><th>Variantes</th><th>Disponibles</th><th>Consommées</th><th>Comptes utilisés</th><th>Statut</th>
          </tr></thead><tbody>` + rows.map(m => `<tr>
            <td>${m.master_code}</td><td class="muted">${new Date(m.created_at).toLocaleDateString()}</td>
            <td>${m.variant_count}</td><td>${m.available_count}</td><td class="muted">${m.consumed_count}</td>
            <td class="muted">${m.accounts_used}</td><td><span class="badge">${m.status}</span></td>
          </tr>`).join('') + `</tbody></table>`;
      }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    }
    load();
    </script>
    """
    return _page("/demo/masters", "Masters", body)


@router.get("/demo/inventory", response_class=HTMLResponse)
def demo_inventory():
    body = """
    <div id="content">Chargement...</div>
    <script>
    fetch('/inventory?limit=500').then(r => r.json()).then(rows => {
      if (!rows.length) { document.getElementById('content').innerHTML = '<div class="empty">Rien à afficher.</div>'; return; }
      document.getElementById('content').innerHTML = `<table><thead><tr>
        <th>Master</th><th>Variante</th><th>Caption</th><th>Compte</th><th>Date</th><th>Statut</th>
        </tr></thead><tbody>` + rows.map(r => `<tr>
          <td class="muted">${r.master_code}</td><td>${r.variant_code}</td>
          <td class="muted">${r.caption_text || '—'}</td><td>${r.account_username || '—'}</td>
          <td class="muted">${r.scheduled_at_utc ? new Date(r.scheduled_at_utc).toLocaleString() : '—'}</td>
          <td><span class="badge">${r.status}</span></td>
        </tr>`).join('') + `</tbody></table>`;
    }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    </script>
    """
    return _page("/demo/inventory", "Inventaire", body)


@router.get("/demo/calendar", response_class=HTMLResponse)
def demo_calendar():
    body = """
    <div class="actions">
      <button class="primary" onclick="generatePlan()">GÉNÉRER LE PLAN 30 JOURS</button>
    </div>
    <div id="content">Chargement...</div>
    <script>
    function load() {
      fetch('/calendar/plans?limit=100').then(r => r.json()).then(rows => {
        if (!rows.length) { document.getElementById('content').innerHTML = '<div class="empty">Aucun plan pour l\\'instant.</div>'; return; }
        document.getElementById('content').innerHTML = rows.map(p => {
          const params = p.params || {};
          const approveBtn = (p.status === 'DRAFT' || p.status === 'REVIEW')
            ? `<button onclick="approvePlan('${p.id}')">APPROUVER</button>` : '';
          return `<div class="card" style="margin-bottom:0.75rem">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div><span class="badge">${p.status}</span> <span class="muted">${new Date(p.created_at).toLocaleString()}</span></div>
              ${approveBtn}
            </div>
            <div class="grid" style="margin-top:0.75rem;margin-bottom:0">
              <div><div class="label">Requis</div><div class="value">${params.required_posts ?? '—'}</div></div>
              <div><div class="label">Disponible</div><div class="value">${params.available_variants_at_start ?? '—'}</div></div>
              <div><div class="label">Réservé</div><div class="value">${params.reserved_count ?? '—'}</div></div>
              <div><div class="label">Manque</div><div class="value">${params.shortage ?? '—'}</div></div>
            </div>
          </div>`;
        }).join('');
      }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    }
    function generatePlan() {
      fetch('/calendar/generate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
        .then(r => r.json()).then(() => load())
        .catch(e => alert('Erreur : ' + e));
    }
    function approvePlan(id) {
      fetch('/calendar/approve/' + id, {method: 'POST'}).then(() => load()).catch(e => alert('Erreur : ' + e));
    }
    load();
    </script>
    """
    return _page("/demo/calendar", "Calendrier", body)


@router.get("/demo/queue", response_class=HTMLResponse)
def demo_queue():
    body = """
    <div class="actions">
      <button onclick="runNow()">LANCER MAINTENANT</button>
      <button class="warn" id="pauseBtn" onclick="togglePause()">...</button>
    </div>
    <div id="stats" class="grid"></div>
    <div id="content">Chargement...</div>
    <script>
    let paused = false;
    function load() {
      Promise.all([
        fetch('/publishing/status').then(r => r.json()),
        fetch('/publishing/jobs?limit=200').then(r => r.json()),
      ]).then(([status, jobs]) => {
        paused = status.paused;
        document.getElementById('pauseBtn').textContent = paused ? 'REPRENDRE' : 'TOUT METTRE EN PAUSE';
        const by = status.by_status || {};
        document.getElementById('stats').innerHTML = `
          <div class="card"><div class="label">Worker</div><div class="value">${paused ? 'En pause' : 'Actif'}</div></div>
          <div class="card"><div class="label">Dus maintenant</div><div class="value">${status.due_now}</div></div>
          <div class="card"><div class="label">Programmés</div><div class="value">${by.SCHEDULED || 0}</div></div>
          <div class="card"><div class="label">Publiés</div><div class="value">${by.PUBLISHED || 0}</div></div>`;
        document.getElementById('content').innerHTML = jobs.length ? `<table><thead><tr>
          <th>Compte</th><th>Variante</th><th>Programmé</th><th>Statut</th><th>Tentatives</th><th>Erreur</th>
          </tr></thead><tbody>` + jobs.map(j => `<tr>
            <td>${j.account_username || '—'}</td><td>${j.variant_code || '—'}</td>
            <td class="muted">${j.scheduled_at_utc ? new Date(j.scheduled_at_utc).toLocaleString() : '—'}</td>
            <td><span class="badge">${j.status}</span></td><td class="muted">${j.attempts}</td>
            <td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${j.last_error || ''}</td>
          </tr>`).join('') + `</tbody></table>` : '<div class="empty">Aucune tâche pour l\\'instant.</div>';
      }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    }
    function runNow() { fetch('/publishing/start', {method: 'POST'}).then(() => load()); }
    function togglePause() {
      fetch('/publishing/' + (paused ? 'resume' : 'pause'), {method: 'POST'}).then(() => load());
    }
    load();
    </script>
    """
    return _page("/demo/queue", "Queue", body)


@router.get("/demo/errors", response_class=HTMLResponse)
def demo_errors():
    body = """
    <div id="content">Chargement...</div>
    <script>
    fetch('/logs?limit=200').then(r => r.json()).then(rows => {
      if (!rows.length) { document.getElementById('content').innerHTML = '<div class="empty">Aucune erreur enregistrée. Bon signe.</div>'; return; }
      document.getElementById('content').innerHTML = `<table><thead><tr>
        <th>Date</th><th>Code</th><th>Message</th>
        </tr></thead><tbody>` + rows.map(l => `<tr>
          <td class="muted">${new Date(l.timestamp).toLocaleString()}</td>
          <td><span class="badge badge-${l.level === 'ERROR' ? 'bad' : l.level === 'WARNING' ? 'warn' : ''}">${l.code || l.level}</span></td>
          <td>${l.message}</td>
        </tr>`).join('') + `</tbody></table>`;
    }).catch(e => document.getElementById('content').innerHTML = '<div class="empty">Erreur : ' + e + '</div>');
    </script>
    """
    return _page("/demo/errors", "Erreurs", body)
