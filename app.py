from flask import Flask, request, jsonify, send_from_directory, Response
import datetime, json, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_DIR, "ip_log.txt")

app = Flask(__name__, static_folder=".")

def client_ip(req):
    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return req.remote_addr or "0.0.0.0"

def log_visit(req):
    entry = {
        "ts": datetime.datetime.now().astimezone().isoformat(),
        "ip": client_ip(req),
        "method": req.method,
        "path": req.path,
        "origin": req.headers.get("Origin", ""),
        "referer": req.headers.get("Referer", ""),
        "ua": req.headers.get("User-Agent", ""),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

@app.route("/")
def root():
    return send_from_directory(APP_DIR, "index.html")

@app.route("/get_ip")
def get_ip():
    entry = log_visit(request)
    return jsonify({"ip": entry["ip"], "ts": entry["ts"]})

@app.route("/logs.json")
def logs_json():
    items = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try: items.append(json.loads(line))
                    except: pass
    return jsonify(items[-500:])

@app.route("/logs")
def logs_page():
    html = """
<!DOCTYPE html><meta charset="utf-8"><title>訪客 IP 記錄</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,"Noto Sans TC";padding:16px;background:#0b1020;color:#e6eefc}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{padding:8px 10px;border-bottom:1px solid #1d2b43;font-size:13px}
th{text-align:left;color:#91a4bf}
code{color:#9ad1ff}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #2b3b57;color:#91a4bf}
</style>
<h1>訪客 IP 記錄 <span class="badge">最近 500 筆</span></h1>
<div>每 3 秒自動更新：時間、IP、方法、路徑、Origin、Referer、User-Agent。</div>
<table id="tbl"><thead><tr><th>#</th><th>時間</th><th>IP</th><th>方法</th><th>路徑</th><th>Origin</th><th>Referer</th><th>User-Agent</th></tr></thead><tbody></tbody></table>
<script>
async function loadLogs(){
  const res = await fetch('/logs.json',{cache:'no-store'});
  const items = await res.json();
  const tb = document.querySelector('#tbl tbody'); tb.innerHTML='';
  const esc = s => String(s||'').replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  items.forEach((it,i)=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${i+1}</td><td><code>${esc(it.ts)}</code></td><td><code>${esc(it.ip)}</code></td>
      <td>${esc(it.method)}</td><td>${esc(it.path)}</td><td>${esc(it.origin)}</td><td>${esc(it.referer)}</td><td>${esc(it.ua)}</td>`;
    tb.appendChild(tr);
  });
}
loadLogs(); setInterval(loadLogs,3000);
</script>"""
    return Response(html, mimetype="text/html")

@app.route("/simulator")
def simulator():
    name = "attack_simulator_integrated_full.html"
    if os.path.exists(os.path.join(APP_DIR, name)):
        return send_from_directory(APP_DIR, name)
    return Response("<h1>Simulator not found</h1><p>把攻擊模擬器 HTML 放在專案根目錄後再訪問 /simulator。</p>", mimetype="text/html")

@app.route("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))