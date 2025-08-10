from flask import Flask, request, jsonify, send_from_directory, Response
import datetime, json, os, csv, io, ipaddress, urllib.request, urllib.error

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_DIR, "ip_log.txt")
GEO_CACHE_FILE = os.path.join(APP_DIR, "geo_cache.json")

app = Flask(__name__, static_folder=".")

# --- GeoIP cache ---
if os.path.exists(GEO_CACHE_FILE):
    try:
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            GEO_CACHE = json.load(f)
    except Exception:
        GEO_CACHE = {}
else:
    GEO_CACHE = {}  # { ip: {"country":"", "city":"", "org":"", "ts":"..."} }

def save_geo_cache():
    try:
        with open(GEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(GEO_CACHE, f, ensure_ascii=False)
    except Exception:
        pass

def is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except Exception:
        return False

def client_ip(req):
    # 優先取 X-Forwarded-For 第一個 IP（前面有 CDN/反代時）
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

def fetch_geo_from_provider(ip: str) -> dict:
    """向免費服務 ipapi.co 查詢 GeoIP。若不想外連，可設環境變數 GEOIP_OFF=1。"""
    if os.environ.get("GEOIP_OFF") == "1":
        return {"country":"", "city":"", "org":"", "provider":"off"}
    url = f"https://ipapi.co/{ip}/json/"
    req = urllib.request.Request(url, headers={"User-Agent": "ip-logger/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
            return {
                "country": data.get("country_name") or data.get("country") or "",
                "city": data.get("city") or "",
                "org": data.get("org") or data.get("asn") or "",
                "provider": "ipapi.co"
            }
    except Exception:
        # 失敗就回空，避免阻塞
        return {"country":"", "city":"", "org":"", "provider":"error"}

def geo_lookup(ip: str) -> dict:
    if not ip or is_private(ip) or ip in ("127.0.0.1", "::1"):
        return {"ip": ip, "country": "(private)", "city": "", "org": ""}
    cached = GEO_CACHE.get(ip)
    if cached:
        return {"ip": ip, **cached}
    info = fetch_geo_from_provider(ip)
    GEO_CACHE[ip] = {k: info.get(k, "") for k in ("country", "city", "org")}
    save_geo_cache()
    return {"ip": ip, **GEO_CACHE[ip]}

# --- Routes ---

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
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
    return jsonify(items[-500:])  # 只回傳最近 500 筆

@app.route("/logs.csv")
def logs_csv():
    # 匯出最近 n 筆（預設 500，最多 5000）
    try:
        n = max(1, min(int(request.args.get("n", "500")), 5000))
    except Exception:
        n = 500
    rows = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    rows = rows[-n:]

    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(["ts", "ip", "method", "path", "origin", "referer", "ua"])
    for r in rows:
        w.writerow([r.get("ts",""), r.get("ip",""), r.get("method",""), r.get("path",""),
                    r.get("origin",""), r.get("referer",""), r.get("ua","")])
    out = sio.getvalue()
    return Response(out, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="logs_last_{len(rows)}.csv"'})

@app.route("/geo")
def geo():
    ip = (request.args.get("ip") or "").strip()
    if not ip:
        return jsonify({"error":"missing ip"}), 400
    return jsonify(geo_lookup(ip))

@app.route("/logs")
def logs_page():
    # 單檔 HTML，含 GeoIP 欄與 CSV 匯出
    html = """
<!DOCTYPE html>
<html lang="zh-Hant"><meta charset="utf-8">
<title>訪客 IP 記錄</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,"Noto Sans TC";padding:16px;background:#0b1020;color:#e6eefc}
.topbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.btn{display:inline-block;padding:8px 12px;border-radius:10px;border:1px solid #2b3b57;background:#0d1620;color:#e6eefc;text-decoration:none}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #2b3b57;color:#91a4bf}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{padding:8px 10px;border-bottom:1px solid #1d2b43;font-size:13px}
th{text-align:left;color:#91a4bf}
code{color:#9ad1ff}
.small{font-size:12px;color:#91a4bf}
</style>
<h1>訪客 IP 記錄 <span class="badge" id="count">最近 0 筆</span></h1>
<div class="topbar">
  <a class="btn" id="csv" href="/logs.csv?n=500">Export CSV</a>
  <span class="small">資料每 3 秒自動更新；GeoIP 由 ipapi.co 提供並做快取。</span>
</div>

<table id="tbl">
  <thead><tr>
    <th>#</th><th>時間</th><th>IP</th><th>GeoIP</th>
    <th>方法</th><th>路徑</th><th>Origin</th><th>Referer</th><th>User-Agent</th>
  </tr></thead>
  <tbody></tbody>
</table>

<script>
const tb = document.querySelector('#tbl tbody');
const count = document.getElementById('count');
const inMemoryGeo = {}; // 本頁快取，避免重複查詢

function esc(s){ return String(s||'').replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

async function fetchGeo(ip){
  if (!ip || inMemoryGeo[ip]) return inMemoryGeo[ip] || {country:"",city:"",org:""};
  try {
    const res = await fetch('/geo?ip='+encodeURIComponent(ip), {cache:'no-store'});
    const g = await res.json();
    inMemoryGeo[ip] = { country: g.country||"", city: g.city||"", org: g.org||"" };
  } catch(e){ inMemoryGeo[ip] = {country:"", city:"", org:""}; }
  return inMemoryGeo[ip];
}

async function loadLogs(){
  const res = await fetch('/logs.json', {cache:'no-store'});
  const items = await res.json();
  count.textContent = "最近 " + items.length + " 筆";
  tb.innerHTML = "";

  // 先收集需要查詢的唯一 IP
  const uniq = [...new Set(items.map(x => x.ip))];
  await Promise.all(uniq.map(ip => fetchGeo(ip)));

  items.forEach((it, i)=>{
    const g = inMemoryGeo[it.ip] || {};
    const geo = [g.country, g.city, g.org].filter(Boolean).join(" · ");
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${i+1}</td>
      <td><code>${esc(it.ts)}</code></td>
      <td><code>${esc(it.ip)}</code></td>
      <td>${esc(geo)}</td>
      <td>${esc(it.method)}</td>
      <td>${esc(it.path)}</td>
      <td>${esc(it.origin)}</td>
      <td>${esc(it.referer)}</td>
      <td>${esc(it.ua)}</td>`;
    tb.appendChild(tr);
  });
}
loadLogs();
setInterval(loadLogs, 3000);
</script>
"""
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
    # 本機或 Replit 開發
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
