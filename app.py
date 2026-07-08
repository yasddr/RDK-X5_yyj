import socket

# 自动取本机所有 IPv4（第一个非 127.0.0.1），iframe 里用它嵌 ROS2 画面；
# IP 变了不用再改 HTML
def _board_ip():
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                return ip
    except Exception:
        pass
    return '127.0.0.1'

import os, time, json, threading, subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError
from collections import deque
from flask import Flask, Response, render_template, jsonify
from flask import request as flask_request  # 用于 /api/sos/trigger

app = Flask(__name__)

# 静态资源禁用缓存（避免浏览器缓存 app.js 后按钮点击不响应）
@app.after_request
def _no_cache(resp):
    if resp.headers.get('Content-Type', '').startswith(('text/html', 'application/javascript', 'text/css')):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp
PORT = int(os.environ.get("PORT", "8000"))

state = {"voice": False, "voice_pid": None,
         "voice_user": "", "voice_ai": ""}
sl = threading.Lock()

# 对话历史（最近 100 条，环形缓冲）
history = deque(maxlen=100)
sl_hist = threading.Lock()

# ==================== 天气（wttr.in 代理，按板子 IP 定位，5 分钟缓存）====================
_weather_cache = {"ts": 0, "data": None, "err": None}
_weather_lock = threading.Lock()
WEATHER_TTL = 300  # 5 分钟

def fetch_weather():
    """调 wttr.in 取当前 + 3 天预报（含小时级）。一次 API 调用即可。"""
    with _weather_lock:
        now = time.time()
        if _weather_cache["data"] and now - _weather_cache["ts"] < WEATHER_TTL:
            return _weather_cache["data"], None
        try:
            req = Request("https://wttr.in/?format=j1&lang=zh",
                          headers={"User-Agent": "curl/7.81", "Accept-Language": "zh"})
            with urlopen(req, timeout=10) as r:
                raw = r.read().decode("utf-8", errors="replace")
            d = json.loads(raw)
            cur = d["current_condition"][0]
            area = d.get("nearest_area", [{}])[0]
            city = (area.get("areaName") or [{"value": "未知"}])[0].get("value", "未知")
            region = (area.get("region") or [{"value": ""}])[0].get("value", "")
            country = (area.get("country") or [{"value": ""}])[0].get("value", "")
            data = {
                "city": city, "region": region, "country": country,
                "now": {
                    "tempC": cur.get("temp_C"),
                    "feelsC": cur.get("FeelsLikeC"),
                    "humidity": cur.get("humidity"),
                    "desc": (cur.get("weatherDesc") or [{"value": ""}])[0].get("value", ""),
                    "windKmph": cur.get("windspeedKmph"),
                    "windDir": cur.get("winddir16Point"),
                    "pressure": cur.get("pressure"),
                    "visibility": cur.get("visibility"),
                    "cloudcover": cur.get("cloudcover"),
                    "uv": cur.get("uvIndex"),
                },
                "forecast": [
                    {
                        "date": day.get("date"),
                        "maxC": day.get("maxtempC"),
                        "minC": day.get("mintempC"),
                        "sunrise": (day.get("astronomy") or [{}])[0].get("sunrise", ""),
                        "sunset": (day.get("astronomy") or [{}])[0].get("sunset", ""),
                        "hours": [
                            {
                                "time": h.get("time"),
                                "tempC": h.get("tempC"),
                                "feelsC": h.get("FeelsLikeC"),
                                "desc": (h.get("weatherDesc") or [{"value": ""}])[0].get("value", ""),
                                "chance": h.get("chanceofrain"),
                                "humidity": h.get("humidity"),
                            }
                            for h in day.get("hourly", [])
                        ],
                    }
                    for day in d.get("weather", [])
                ],
            }
            _weather_cache["ts"] = now
            _weather_cache["data"] = data
            _weather_cache["err"] = None
            return data, None
        except (URLError, KeyError, ValueError, TimeoutError) as e:
            err = f"{type(e).__name__}: {e}"
            _weather_cache["err"] = err
            return None, err

sse_clients = []
sse_lock = threading.Lock()

def push(typ, data):
    msg = f"event: {typ}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with sse_lock:
        for q in sse_clients[:]:
            try:
                q.put_nowait(msg)
            except:
                sse_clients.remove(q)

def add_history(role, text):
    """添加一条对话到历史（role: user/ai）"""
    item = {"role": role, "text": text, "ts": time.time()}
    with sl_hist:
        history.append(item)
    push("history", item)

# ==================== 语音助手 ====================
voice_proc = None

def start_voice():
    global voice_proc
    if voice_proc and voice_proc.poll() is None:
        return False, "running"
    sc = "/home/sunrise/voice_ws/src/server_vad_mode.py"
    if not os.path.exists(sc):
        return False, "no script"
    env = os.environ.copy()
    env["DASHSCOPE_API_KEY"] = os.environ.get("DASHSCOPE_API_KEY", "")
    env["PYTHONUNBUFFERED"] = "1"
    voice_proc = subprocess.Popen(
        ["python3", "-u", sc],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, env=env)
    with sl:
        state["voice"] = True
        state["voice_pid"] = voice_proc.pid
    push("voice", {"type": "started", "pid": voice_proc.pid})
    threading.Thread(target=watch_voice, daemon=True).start()
    return True, f"pid={voice_proc.pid}"

def stop_voice():
    global voice_proc
    if not voice_proc or voice_proc.poll() is not None:
        voice_proc = None
        with sl:
            state["voice"] = False
        return True, "stopped"
    voice_proc.terminate()
    try:
        voice_proc.wait(2)
    except:
        voice_proc.kill()
    voice_proc = None
    with sl:
        state["voice"] = False
    push("voice", {"type": "stopped"})
    return True, "stopped"

def watch_voice():
    """解析 voice 子进程输出中的用户/AI 对话。"""
    global voice_proc
    while voice_proc and voice_proc.poll() is None:
        line = voice_proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        try:
            s = line.decode("utf-8", errors="replace").rstrip()
        except Exception:
            continue
        if not s:
            continue
        if "👤 用户:" in s or "🎤 你说:" in s:
            t = s.split("👤 用户:", 1)[-1].split("🎤 你说:", 1)[-1].strip()
            if t:
                with sl:
                    state["voice_user"] = t
                push("voice", {"type": "user", "text": t})
                add_history("user", t)
        elif "🤖 地瓜派:" in s or "🤖 AI:" in s:
            t = s.split("🤖 地瓜派:", 1)[-1].split("🤖 AI:", 1)[-1].strip()
            if t:
                with sl:
                    state["voice_ai"] = t
                push("voice", {"type": "ai", "text": t})
                add_history("ai", t)
    with sl:
        state["voice"] = False
    push("voice", {"type": "stopped"})

# ==================== Flask 路由 ====================
# ==================== 紧急求助配置 ====================
# 联系人/医院/热线集中在这里，改动后只需重启服务；后续可以走 JSON 配置文件
SOS_CONTACTS = [
    {"name": "家人（父亲）", "phone": "13800001111", "tag": "家庭", "icon": "👨"},
    {"name": "家人（母亲）", "phone": "13800002222", "tag": "家庭", "icon": "👩"},
    {"name": "子女",         "phone": "13800003333", "tag": "家庭", "icon": "🧒"},
    {"name": "社区医生",     "phone": "0551-12345678", "tag": "社区", "icon": "🏥"},
]
SOS_HOTLINES = [
    {"name": "急救 120",       "phone": "120",      "icon": "🚑", "desc": "医疗急救"},
    {"name": "报警 110",       "phone": "110",      "icon": "🚓", "desc": "公安报警"},
    {"name": "火警 119",       "phone": "119",      "icon": "🚒", "desc": "火灾救援"},
    {"name": "交通事故 122",   "phone": "122",      "icon": "🚧", "desc": "交通事故报警"},
    {"name": "12345 市民热线", "phone": "12345",    "icon": "📞", "desc": "政务服务"},
    {"name": "心理援助 12320", "phone": "12320",    "icon": "💚", "desc": "卫生热线"},
]
SOS_HOSPITALS = [
    {"name": "合肥市第一人民医院", "phone": "0551-62181114", "address": "合肥市淮河路 390 号", "distance": "约 2.1 km"},
    {"name": "安徽医科大学第一附属医院", "phone": "0551-62922004", "address": "合肥市绩溪路 218 号", "distance": "约 3.2 km"},
    {"name": "安徽省立医院", "phone": "0551-62283114", "address": "合肥市庐江路 17 号", "distance": "约 4.5 km"},
]
SOS_USER = {
    "name":    "本人",
    "blood":   "A 型",
    "allergy": "青霉素",
    "address": "合肥市蜀山区 XX 小区 X 栋 X 单元",
}

@app.route('/')
def idx():
    ip = _board_ip()
    return render_template('index.html', board_ip=ip, ros2_port=8081, flask_port=8000, page='home')

@app.route('/temperature')
def temp():
    ip = _board_ip()
    return render_template('temperature.html', board_ip=ip, ros2_port=8081, flask_port=8000, page='temp')

@app.route('/air_quality')
def air():
    ip = _board_ip()
    return render_template('air_quality.html', board_ip=ip, ros2_port=8081, flask_port=8000, page='air')

@app.route('/weather')
def weather():
    ip = _board_ip()
    return render_template('weather.html', board_ip=ip, ros2_port=8081, flask_port=8000, page='weather')

@app.route('/sos')
def sos():
    ip = _board_ip()
    return render_template('sos.html',
                           board_ip=ip, ros2_port=8081, flask_port=8000,
                           page='sos',
                           contacts=SOS_CONTACTS,
                           hotlines=SOS_HOTLINES,
                           hospitals=SOS_HOSPITALS,
                           user=SOS_USER)

@app.route('/api/sos')
def sos_api():
    return jsonify({"ok": True,
                    "contacts": SOS_CONTACTS,
                    "hotlines": SOS_HOTLINES,
                    "hospitals": SOS_HOSPITALS,
                    "user": SOS_USER})

@app.route('/api/weather')
def weather_api():
    data, err = fetch_weather()
    if data is None:
        return jsonify({"ok": False, "err": err or "unknown"}), 502
    return jsonify({"ok": True, "data": data, "ts": _weather_cache["ts"]})

@app.route('/api/status')
def st():
    with sl:
        return jsonify(dict(state))

@app.route('/api/history')
def hist():
    with sl_hist:
        return jsonify(list(history))

@app.route('/api/history/clear', methods=['POST'])
def hist_clear():
    with sl_hist:
        history.clear()
    push("history_clear", {})
    return jsonify({"ok": True})

@app.route('/api/voice/start', methods=['POST'])
def vs():
    ok, m = start_voice()
    return jsonify({"ok": ok, "msg": m})

@app.route('/api/voice/stop', methods=['POST'])
def vst():
    ok, m = stop_voice()
    return jsonify({"ok": ok, "msg": m})

@app.route('/events')
def sse():
    import queue
    q = queue.Queue(maxsize=200)
    with sse_lock:
        sse_clients.append(q)

    def gen():
        try:
            with sl:
                snap = dict(state)
            with sl_hist:
                hist_snap = list(history)
            init_data = {"state": snap, "history": hist_snap}
            yield f"event: init\ndata: {json.dumps(init_data, ensure_ascii=False)}\n\n"
            while True:
                try:
                    yield q.get(timeout=10)
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            with sse_lock:
                try:
                    sse_clients.remove(q)
                except:
                    pass

    return Response(gen(), mimetype="text/event-stream")

if __name__ == '__main__':
    print(f"web on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False, debug=False)
