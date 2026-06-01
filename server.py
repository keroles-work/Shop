#!/usr/bin/env python3
"""
NOIR Store — Full Stack Server
Python stdlib only: http.server + sqlite3 + json
API:  /api/products   GET/POST/PUT/DELETE
      /api/upload     POST (image upload)
      /api/orders     GET/POST
      /api/auth/login POST
Static: /             → static/index.html
        /admin        → static/admin.html
        /uploads/...  → uploads/
"""

import http.server
import socketserver
import sqlite3
import json
import os
import base64
import uuid
import hashlib
import time
import re
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# ─────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DB_PATH   = BASE_DIR / "noir.db"
UPLOADS   = BASE_DIR / "uploads"
STATIC    = BASE_DIR / "static"
PORT      = int(os.environ.get('PORT', 8000))
ADMIN_PASS = hashlib.sha256(b"noir2026").hexdigest()   # password: noir2026
# ─────────────────────────────────────────────

UPLOADS.mkdir(exist_ok=True)
STATIC.mkdir(exist_ok=True)

# ── DB SETUP ─────────────────────────────────
def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            brand     TEXT DEFAULT 'NOIR',
            category  TEXT NOT NULL,
            price_jod REAL NOT NULL,
            old_price REAL,
            badge     TEXT,
            emoji     TEXT DEFAULT '🛍',
            image     TEXT,
            description TEXT,
            stock     INTEGER DEFAULT 100,
            active    INTEGER DEFAULT 1,
            created   INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            customer   TEXT NOT NULL,
            phone      TEXT,
            address    TEXT,
            currency   TEXT DEFAULT 'JOD',
            total_jod  REAL NOT NULL,
            items      TEXT NOT NULL,
            status     TEXT DEFAULT 'pending',
            created    INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        INSERT OR IGNORE INTO settings VALUES ('store_name','NOIR');
        INSERT OR IGNORE INTO settings VALUES ('egp_rate','40');
        """)
        # Seed demo products if empty
        c = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if c == 0:
            demos = [
                ("بدلة كلاسيكية مخملية","NOIR","بدل",89.500,None,"جديد","👔",None,"بدلة رجالية فاخرة مصنوعة من أجود أنواع القماش المخملي"),
                ("ساعة كرونوغراف فاخرة","CLASSIQUE","ساعات",62.500,89.000,"تخفيض","⌚",None,"ساعة يد فاخرة بتصميم عصري وحركة سويسرية دقيقة"),
                ("حذاء أوكسفورد جلد طبيعي","NOIR","أحذية",27.500,None,"مميز","👟",None,"حذاء رسمي مصنوع من الجلد الطبيعي الإيطالي"),
                ("وشاح كشمير إيطالي","ÉLITE","إكسسوار",11.250,15.000,None,"🧣",None,"وشاح من الكشمير الإيطالي الفاخر بألوان متعددة"),
                ("محفظة جلدية فاخرة","NOIR","حقائب",18.900,None,"جديد","👜",None,"محفظة رجالية أنيقة من الجلد الطبيعي"),
                ("عطر رجالي أود","MAISON","عطور",35.000,None,None,"🧴",None,"عطر شرقي فاخر بعبق العود والمسك الأصيل"),
            ]
            db.executemany("""INSERT INTO products
                (name,brand,category,price_jod,old_price,badge,emoji,image,description)
                VALUES (?,?,?,?,?,?,?,?,?)""", demos)
        db.commit()

# ── UTILS ─────────────────────────────────────
def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type","application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin","*")
    handler.end_headers()
    handler.wfile.write(body)

def read_body(handler):
    length = int(handler.headers.get("Content-Length",0))
    return handler.rfile.read(length)

def parse_multipart(handler):
    """Simple multipart parser for file upload."""
    ct = handler.headers.get("Content-Type","")
    boundary_match = re.search(r'boundary=([^\s;]+)', ct)
    if not boundary_match:
        return {}, {}
    boundary = ("--" + boundary_match.group(1)).encode()
    body = read_body(handler)
    parts = body.split(boundary)
    fields, files = {}, {}
    for part in parts[1:-1]:
        if b'\r\n\r\n' not in part:
            continue
        header_raw, data = part.split(b'\r\n\r\n', 1)
        data = data.rstrip(b'\r\n')
        headers = header_raw.decode(errors='replace')
        name_m = re.search(r'name="([^"]+)"', headers)
        fname_m = re.search(r'filename="([^"]*)"', headers)
        if not name_m:
            continue
        name = name_m.group(1)
        if fname_m and fname_m.group(1):
            files[name] = {"filename": fname_m.group(1), "data": data}
        else:
            fields[name] = data.decode(errors='replace')
    return fields, files

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ── REQUEST HANDLER ────────────────────────────
class NoirHandler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass   # silence default logging

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization")
        self.end_headers()

    # ── GET ──────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)

        # API routes
        if path == "/api/products":
            with get_db() as db:
                cat   = qs.get("category",[""])[0]
                query = "SELECT * FROM products WHERE active=1"
                params = []
                if cat:
                    query += " AND category=?"
                    params.append(cat)
                query += " ORDER BY created DESC"
                rows = db.execute(query, params).fetchall()
            return json_response(self, rows_to_list(rows))

        if path.startswith("/api/products/"):
            pid = path.split("/")[-1]
            with get_db() as db:
                row = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if row:
                return json_response(self, row_to_dict(row))
            return json_response(self, {"error":"not found"}, 404)

        if path == "/api/orders":
            with get_db() as db:
                rows = db.execute("SELECT * FROM orders ORDER BY created DESC").fetchall()
            return json_response(self, rows_to_list(rows))

        if path == "/api/settings":
            with get_db() as db:
                rows = db.execute("SELECT key,value FROM settings").fetchall()
            return json_response(self, {r["key"]:r["value"] for r in rows})

        if path == "/api/stats":
            with get_db() as db:
                total_p = db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
                total_o = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
                revenue = db.execute("SELECT COALESCE(SUM(total_jod),0) FROM orders").fetchone()[0]
                cats    = db.execute("SELECT category, COUNT(*) as n FROM products WHERE active=1 GROUP BY category").fetchall()
            return json_response(self, {
                "products": total_p, "orders": total_o,
                "revenue_jod": round(revenue,3),
                "categories": rows_to_list(cats)
            })

        # Static files
        if path in ("/", ""):
            return self._serve_file(STATIC / "index.html")
        if path == "/admin":
            return self._serve_file(STATIC / "admin.html")
        if path.startswith("/uploads/"):
            fname = path[9:]
            return self._serve_file(UPLOADS / fname)
        if path.startswith("/static/"):
            fname = path[8:]
            return self._serve_file(STATIC / fname)

        # Fallback
        return self._serve_file(STATIC / "index.html")

    # ── POST ─────────────────────────────────
    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "/api/auth/login":
            body = json.loads(read_body(self) or b'{}')
            pw   = hashlib.sha256(body.get("password","").encode()).hexdigest()
            if pw == ADMIN_PASS:
                token = base64.b64encode(f"admin:{int(time.time())}".encode()).decode()
                return json_response(self, {"token": token, "ok": True})
            return json_response(self, {"error":"كلمة مرور خاطئة"}, 401)

        if path == "/api/products":
            body = json.loads(read_body(self) or b'{}')
            with get_db() as db:
                cur = db.execute("""
                    INSERT INTO products (name,brand,category,price_jod,old_price,badge,emoji,image,description,stock)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    body.get("name"), body.get("brand","NOIR"),
                    body.get("category"), float(body.get("price_jod",0)),
                    float(body["old_price"]) if body.get("old_price") else None,
                    body.get("badge"), body.get("emoji","🛍"),
                    body.get("image"), body.get("description"),
                    int(body.get("stock",100))
                ))
                db.commit()
                row = db.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone()
            return json_response(self, row_to_dict(row), 201)

        if path == "/api/upload":
            ct = self.headers.get("Content-Type","")
            if "multipart" in ct:
                fields, files = parse_multipart(self)
                f = files.get("image") or files.get("file")
                if not f:
                    return json_response(self, {"error":"no file"}, 400)
                ext  = Path(f["filename"]).suffix.lower() or ".jpg"
                name = str(uuid.uuid4()) + ext
                (UPLOADS / name).write_bytes(f["data"])
                return json_response(self, {"url": f"/uploads/{name}"})
            else:
                # base64 upload
                body = json.loads(read_body(self) or b'{}')
                data_uri = body.get("data","")
                if "," in data_uri:
                    header, b64 = data_uri.split(",",1)
                    ext = ".jpg"
                    if "png" in header: ext = ".png"
                    elif "webp" in header: ext = ".webp"
                    name = str(uuid.uuid4()) + ext
                    (UPLOADS / name).write_bytes(base64.b64decode(b64))
                    return json_response(self, {"url": f"/uploads/{name}"})
                return json_response(self, {"error":"bad data"}, 400)

        if path == "/api/orders":
            body = json.loads(read_body(self) or b'{}')
            with get_db() as db:
                cur = db.execute("""
                    INSERT INTO orders (customer,phone,address,currency,total_jod,items)
                    VALUES (?,?,?,?,?,?)
                """, (
                    body.get("customer","زائر"),
                    body.get("phone",""),
                    body.get("address",""),
                    body.get("currency","JOD"),
                    float(body.get("total_jod",0)),
                    json.dumps(body.get("items",[]), ensure_ascii=False)
                ))
                db.commit()
            return json_response(self, {"id": cur.lastrowid, "ok": True}, 201)

        if path == "/api/settings":
            body = json.loads(read_body(self) or b'{}')
            with get_db() as db:
                for k,v in body.items():
                    db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",(k,str(v)))
                db.commit()
            return json_response(self, {"ok": True})

        return json_response(self, {"error":"not found"}, 404)

    # ── PUT ──────────────────────────────────
    def do_PUT(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path.startswith("/api/products/"):
            pid  = path.split("/")[-1]
            body = json.loads(read_body(self) or b'{}')
            with get_db() as db:
                db.execute("""UPDATE products SET
                    name=?, brand=?, category=?, price_jod=?, old_price=?,
                    badge=?, emoji=?, image=?, description=?, stock=?, active=?
                    WHERE id=?""", (
                    body.get("name"), body.get("brand","NOIR"),
                    body.get("category"), float(body.get("price_jod",0)),
                    float(body["old_price"]) if body.get("old_price") else None,
                    body.get("badge"), body.get("emoji","🛍"),
                    body.get("image"), body.get("description"),
                    int(body.get("stock",100)), int(body.get("active",1)),
                    pid
                ))
                db.commit()
                row = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            return json_response(self, row_to_dict(row))

        if path.startswith("/api/orders/"):
            oid  = path.split("/")[-1]
            body = json.loads(read_body(self) or b'{}')
            with get_db() as db:
                db.execute("UPDATE orders SET status=? WHERE id=?", (body.get("status","pending"), oid))
                db.commit()
            return json_response(self, {"ok": True})

        return json_response(self, {"error":"not found"}, 404)

    # ── DELETE ────────────────────────────────
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        if path.startswith("/api/products/"):
            pid = path.split("/")[-1]
            with get_db() as db:
                db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
                db.commit()
            return json_response(self, {"ok": True})
        return json_response(self, {"error":"not found"}, 404)

    def _serve_file(self, fpath):
        fpath = Path(fpath)
        if not fpath.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return
        ext = fpath.suffix.lower()
        mime = {
            ".html":"text/html;charset=utf-8",".css":"text/css",
            ".js":"application/javascript",".json":"application/json",
            ".jpg":"image/jpeg",".jpeg":"image/jpeg",
            ".png":"image/png",".webp":"image/webp",
            ".svg":"image/svg+xml",".ico":"image/x-icon"
        }.get(ext,"application/octet-stream")
        data = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(data)


# ── MAIN ──────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print(f"""
╔══════════════════════════════════════╗
║   NOIR Store — Full Stack Server     ║
╠══════════════════════════════════════╣
║  🌐  http://localhost:{PORT}           ║
║  🔧  http://localhost:{PORT}/admin     ║
║  📦  API: http://localhost:{PORT}/api  ║
║  🔑  Admin password: noir2026        ║
╚══════════════════════════════════════╝
""")
    with socketserver.TCPServer(("", PORT), NoirHandler) as srv:
        srv.allow_reuse_address = True
        srv.serve_forever()
