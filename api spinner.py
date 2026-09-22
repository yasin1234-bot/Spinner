# ============================================================
# FF SPINNER API - OB55 PRO - @XEROX_MODS
# Flask Version for Termux
# ============================================================

import sys
import os
import json
import asyncio
import aiohttp
import re
import time
import threading
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import blackboxprotobuf

# ================= PROTOBUF IMPORT =================
try:
    import my_pb2
    import output_pb2
except ImportError as e:
    print(f"\n[!] PROTOBUF IMPORT ERROR: {e}")
    print(f"[!] Current folder: {os.getcwd()}")
    print(f"[!] my_pb2.py exists: {os.path.exists('my_pb2.py')}")
    print(f"[!] output_pb2.py exists: {os.path.exists('output_pb2.py')}")
    print(f"\n[!] FIX: my_pb2.py এবং output_pb2.py ফাইল এই folder-এ রাখুন।\n")
    sys.exit(1)


# ================= FLASK APP =================
app = Flask(__name__)


# ================= FOLDERS =================
RESULT_FOLDER = "SEXTYMODS SPINNER RESULT"
os.makedirs(RESULT_FOLDER, exist_ok=True)

ALL_ITEMS_FILE = os.path.join(RESULT_FOLDER, "all_items.json")
FAILED_FILE    = os.path.join(RESULT_FOLDER, "failed_accounts.json")
LOG_FILE       = os.path.join(RESULT_FOLDER, "terminal_log.txt")
SUMMARY_FILE   = os.path.join(RESULT_FOLDER, "summary_list.txt")

category_locks = {
    "ultra_rare.json": threading.Lock(),
    "other_items.json": threading.Lock()
}
all_items_lock   = threading.Lock()
failed_file_lock = threading.Lock()
log_file_lock    = threading.Lock()

# ================= AES =================
AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# ================= SERVERS =================
SERVERS = {
    "bd":  {"code": "bd",  "name": "Bangladesh", "url": "https://clientbp.ggpolarbear.com"},
    "ind": {"code": "ind", "name": "India",      "url": "https://client.ind.freefiremobile.com"}
}

RELEASE_VERSION = "OB55"
RAW_HEX_PAYLOAD = "7FCB76B6CB40C0FFD3FBBDDA4600C039"
EXTERNAL_JWT_API = "https://ff-fast-jwt-api-ob55.vercel.app/guest_to_jwt"

# ================= ITEMS =================
RARE_ITEMS_DB = {
    710047022: "NARUTO BUNDLE",
    801055004: "NARUTO TOKEN",
    820981015: "BLUE NINJA VOUCHER",
    903047008: "Loot Box - Body Substitution - NONE",
    904047008: "Backpack - Ninja's Scroll - NONE",
    907104746: "Gloo Wall - Hokage Rock - NONE",
    909047015: "Rasengan - NONE"
}
ULTRA_RARE_IDS = {710047022}


# ================= ASYNC HELPER FOR FLASK =================
def run_async(coro):
    """Run async function from sync Flask route safely inside threads."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ================= HELPERS =================
def get_item_category(item_name, item_id):
    if item_id in ULTRA_RARE_IDS or "NARUTO BUNDLE" in item_name.upper():
        return "ULTRA RARE", "ultra_rare.json"
    return "Other Items", "other_items.json"


def encrypt_plaintext(plaintext):
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def find_item_id(data):
    if isinstance(data, dict):
        if (1 in data or "1" in data):
            sub = data.get(1) or data.get("1")
            if isinstance(sub, dict):
                if 2 in sub: return sub[2]
                if "2" in sub: return sub["2"]
        for v in data.values():
            r = find_item_id(v)
            if r is not None: return r
    elif isinstance(data, list):
        for item in data:
            r = find_item_id(item)
            if r is not None: return r
    return None


def log(msg):
    ts = datetime.now().strftime("[%H:%M:%S]")
    clean = re.sub(r'\033\[[0-9;]*m', '', f"{ts} {msg}")
    print(clean, flush=True)
    with log_file_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(clean + "\n")


def save_all_item(uid, pwd, item_id, item_name):
    entry = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
             "guestUid": uid, "guestPass": pwd,
             "item_id": item_id, "item_name": item_name}
    with all_items_lock:
        data_list = []
        if os.path.exists(ALL_ITEMS_FILE):
            try:
                with open(ALL_ITEMS_FILE) as f:
                    c = f.read()
                    if c: data_list = json.loads(c)
            except: pass
        data_list.append(entry)
        with open(ALL_ITEMS_FILE, 'w') as f:
            json.dump(data_list, f, indent=4)


def save_categorized_item(uid, pwd, item_id, item_name, filename):
    fp = os.path.join(RESULT_FOLDER, filename)
    entry = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
             "guestUid": uid, "guestPass": pwd,
             "item_id": item_id, "item_name": item_name}
    lock = category_locks.get(filename, threading.Lock())
    with lock:
        data_list = []
        if os.path.exists(fp):
            try:
                with open(fp) as f:
                    c = f.read()
                    if c: data_list = json.loads(c)
            except: pass
        data_list.append(entry)
        with open(fp, 'w') as f:
            json.dump(data_list, f, indent=4)


def append_failed_account(acc):
    with failed_file_lock:
        failed_list = []
        if os.path.exists(FAILED_FILE):
            try:
                with open(FAILED_FILE) as f:
                    c = f.read().strip()
                    if c: failed_list = json.loads(c)
            except: pass
        failed_list.append(acc)
        with open(FAILED_FILE, 'w') as f:
            json.dump(failed_list, f, indent=2)


# ================= TOKEN =================
async def get_token_internal(session, uid, password, retries=3):
    oauth_url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    payload = {
        'uid': uid, 'password': password,
        'response_type': "token", 'client_type': "2",
        'client_secret': "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        'client_id': "100067"
    }
    headers = {'User-Agent': "GarenaMSDK/4.0.19P9"}
    access_token = None
    open_id = None
    for _ in range(retries):
        try:
            async with session.post(oauth_url, data=payload, headers=headers, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    access_token = data.get('access_token')
                    open_id = data.get('open_id')
                    break
        except: await asyncio.sleep(0.5)

    if not access_token or not open_id:
        return None

    login_url = "https://loginbp.ggblueshark.com/MajorLogin"
    login_headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        "Content-Type": "application/octet-stream",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": RELEASE_VERSION
    }
    for platform in [8, 3, 4, 6]:
        try:
            gd = my_pb2.GameData()
            gd.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            gd.game_name = "free fire"
            gd.game_version = 1
            gd.version_code = "1.111.1"
            gd.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
            gd.device_type = "Handheld"
            gd.network_provider = "Verizon Wireless"
            gd.connection_type = "WIFI"
            gd.screen_width = 1280
            gd.screen_height = 960
            gd.dpi = "240"
            gd.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
            gd.total_ram = 5951
            gd.gpu_name = "Adreno (TM) 640"
            gd.gpu_version = "OpenGL ES 3.0"
            gd.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
            gd.ip_address = "172.190.111.97"
            gd.language = "en"
            gd.open_id = open_id
            gd.access_token = access_token
            gd.platform_type = platform
            gd.field_99 = str(platform)
            gd.field_100 = str(platform)

            body = encrypt_plaintext(gd.SerializeToString())
            async with session.post(login_url, data=body, headers=login_headers, ssl=False, timeout=8) as r:
                if r.status == 200:
                    resp_data = await r.read()
                    try:
                        rp = output_pb2.Garena_420()
                        rp.ParseFromString(resp_data)
                        if rp.token: return rp.token
                    except:
                        text = resp_data.decode('utf-8', errors='ignore')
                        s = text.find("eyJ")
                        if s != -1:
                            e = s
                            while e < len(text) and text[e] not in ['"', ' ', '\n', '\r', '\t', '\x00']:
                                e += 1
                            jwt = text[s:e]
                            if jwt.count('.') >= 2: return jwt
        except: pass
        await asyncio.sleep(0.1)
    return None


async def get_token_external(session, uid, password):
    try:
        async with session.get(EXTERNAL_JWT_API, params={"uid": uid, "password": password}, timeout=15) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                except:
                    text = await resp.text()
                    s = text.find("eyJ")
                    if s != -1:
                        e = s
                        while e < len(text) and text[e] not in ['"', ' ', '\n', '\r', '\t', '\x00']:
                            e += 1
                        t = text[s:e]
                        if t.count('.') >= 2: return t
                    return None
                token = data.get("Jwt_Token") or data.get("jwt")
                if token and len(token) > 50 and token.count('.') >= 2:
                    return token
    except: pass
    return None


async def get_token(session, uid, password, retries=3):
    t = await get_token_external(session, uid, password)
    if t: return t
    log(f"[!] External JWT failed for {uid}, trying internal...")
    await asyncio.sleep(0.5)
    return await get_token_internal(session, uid, password, retries)


# ================= SPIN =================
async def send_spin_request(session, url, jwt, payload_hex):
    payload = bytes.fromhex(payload_hex)
    headers = {
        "Authorization": f"Bearer {jwt}",
        "X-GA": "v1 1",
        "ReleaseVersion": RELEASE_VERSION,
        "Content-Type": "application/octet-stream",
        "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"
    }
    try:
        async with session.post(url, headers=headers, data=payload, timeout=20, ssl=False) as resp:
            return resp.status, await resp.read()
    except Exception as e:
        return 0, str(e).encode()


# ================= CORE SPIN FUNCTION =================
async def spin_account(uid: str, password: str, server_name: str = "ind", custom_hex: str = None):
    server_key = (server_name or "ind").lower()
    if server_key not in SERVERS:
        return {"success": False, "uid": uid, "server": server_name,
                "item_id": None, "item_name": None, "category": None,
                "reason": f"Invalid server '{server_name}'. Use bd or ind",
                "raw_status": 0}

    server_info = SERVERS[server_key]
    purchase_url = f"{server_info['url']}/PurchaseGacha"
    spin_hex = custom_hex if custom_hex else RAW_HEX_PAYLOAD

    async with aiohttp.ClientSession() as session:
        try:
            token = await get_token(session, uid, password, 3)
        except Exception as e:
            append_failed_account({"uid": uid, "password": password, "reason": f"Token error: {e}"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": f"Token error: {e}", "raw_status": 0}

        if not token:
            append_failed_account({"uid": uid, "password": password, "reason": "Token failed"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": "Token generation failed", "raw_status": 0}

        try:
            status, spin_resp = await send_spin_request(session, purchase_url, token, spin_hex)
        except Exception as e:
            append_failed_account({"uid": uid, "password": password, "reason": f"Spin error: {e}"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": f"Spin error: {e}", "raw_status": 0}

        if status == 401:
            append_failed_account({"uid": uid, "password": password, "reason": "Token 401"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": "Token 401", "raw_status": 401}

        if status != 200:
            append_failed_account({"uid": uid, "password": password, "reason": f"HTTP {status}"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": f"Spin HTTP {status}", "raw_status": status}

        try:
            decoded, _ = blackboxprotobuf.decode_message(spin_resp)
            item_id = find_item_id(decoded)
            if item_id is None:
                append_failed_account({"uid": uid, "password": password, "reason": "No item ID"})
                return {"success": False, "uid": uid, "server": server_key,
                        "item_id": None, "item_name": None, "category": None,
                        "reason": "No item ID in response", "raw_status": 200}

            item_name = RARE_ITEMS_DB.get(item_id, f"Unknown Item ({item_id})")
            save_all_item(uid, password, item_id, item_name)
            category, target_file = get_item_category(item_name, item_id)
            save_categorized_item(uid, password, item_id, item_name, target_file)

            if category == "ULTRA RARE":
                with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[ULTRA RARE] UID: {uid} | Pass: {password} | Item: {item_name} | ID: {item_id}\n")
            elif item_id in RARE_ITEMS_DB:
                with open(SUMMARY_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{category}] UID: {uid} | Pass: {password} | Item: {item_name} | ID: {item_id}\n")

            log(f"[OK] UID {uid} -> {item_name} (ID: {item_id}) | {category}")

            return {"success": True, "uid": uid, "server": server_key,
                    "item_id": item_id, "item_name": item_name,
                    "category": category, "reason": None, "raw_status": 200}

        except Exception as e:
            append_failed_account({"uid": uid, "password": password, "reason": f"Decode error: {e}"})
            return {"success": False, "uid": uid, "server": server_key,
                    "item_id": None, "item_name": None, "category": None,
                    "reason": f"Decode error: {e}", "raw_status": 200}


# ============================================================
# ================= FLASK ROUTES =============================
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": True,
        "tool": "FF SPINNER OB55 PRO API",
        "dev": "@XEROX_MODS",
        "usage": "/naruto-spin?uid=XXX&pass=YYY&server_name=ind",
        "servers": ["bd", "ind"]
    })


@app.route("/naruto-spin", methods=["GET"])
def naruto_spin_get():
    uid = request.args.get("uid")
    password = request.args.get("pass")
    server_name = request.args.get("server_name", "ind")
    hex_payload = request.args.get("hex_payload")

    if not uid or not password:
        return jsonify({"success": False, "reason": "uid and pass required"}), 400

    if server_name.lower() not in SERVERS:
        return jsonify({
            "success": False,
            "reason": f"server must be one of {list(SERVERS.keys())}"
        }), 400

    try:
        result = run_async(spin_account(uid, password, server_name, hex_payload))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "reason": f"Server error: {e}"}), 500


@app.route("/naruto-spin", methods=["POST"])
def naruto_spin_post():
    data = request.get_json(silent=True) or {}

    uid = data.get("uid")
    password = data.get("password")
    server_name = data.get("server_name", "ind")
    custom_hex = data.get("custom_hex")

    if not uid or not password:
        return jsonify({"success": False, "reason": "uid and password required"}), 400

    if server_name.lower() not in SERVERS:
        return jsonify({
            "success": False,
            "reason": f"server must be one of {list(SERVERS.keys())}"
        }), 400

    try:
        result = run_async(spin_account(uid, password, server_name, custom_hex))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "reason": f"Server error: {e}"}), 500


@app.route("/servers", methods=["GET"])
def servers():
    return jsonify({"servers": [{"key": k, **v} for k, v in SERVERS.items()]})


@app.route("/items", methods=["GET"])
def items():
    return jsonify({"ultra_rare_ids": list(ULTRA_RARE_IDS), "rare_items": RARE_ITEMS_DB})


def _load_json(p):
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                c = f.read()
                if c: return json.loads(c)
        except: pass
    return []


@app.route("/results", methods=["GET"])
def results():
    return jsonify({
        "all_items": _load_json(ALL_ITEMS_FILE),
        "failed": _load_json(FAILED_FILE),
        "ultra_rare": _load_json(os.path.join(RESULT_FOLDER, "ultra_rare.json")),
        "other_items": _load_json(os.path.join(RESULT_FOLDER, "other_items.json"))
    })


@app.route("/files/<path:filename>", methods=["GET"])
def download(filename):
    safe = os.path.basename(filename)
    fp = os.path.join(RESULT_FOLDER, safe)
    if not os.path.exists(fp):
        return jsonify({"error": "file not found"}), 404
    return send_from_directory(RESULT_FOLDER, safe, as_attachment=True)


# ============================================================
# ================= RUN (Termux + Vercel Both) ===============
# ============================================================
handler = app

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  🔥 FF SPINNER API - OB55 PRO - YASIN")
    print("="*60)
    print("  Server running at:  http://0.0.0.0:8000")
    print("  Test Spin:          http://localhost:8000/naruto-spin?uid=UID&pass=PASS&server_name=ind")
    print("="*60 + "\n")

    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)