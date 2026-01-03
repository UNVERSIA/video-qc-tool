import os
import sys
import cv2
import json
import datetime
import re
import socket  
import threading
import webbrowser
from threading import Timer
import tkinter as tk
from tkinter import filedialog
from flask import Flask, render_template_string, request, jsonify, session, redirect


def resource_path(relative_path):
    try:
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


app = Flask(__name__, static_folder=resource_path('static'))
app.secret_key = 'video_qc_secret_key_2025'

STANDARDS = {
    "target_fps": 30,
    "fps_tolerance": 0.5,
    "format": ".mp4",
    "min_width": 2800,
    "min_height": 2100,
    "target_ratio": 4 / 3,
    "ratio_tolerance": 0.05
}
HISTORY_FILE = 'qc_history_db.json'


def find_free_port(start_port=5000):
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            res = sock.connect_ex(('127.0.0.1', port))
            if res != 0:
                return port
            else:
                port += 1
    return 5000


# 后端
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []


def save_history_record(record):
    history = load_history()
    history.append(record)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def open_folder_dialog():
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder_path = filedialog.askdirectory(title="选择文件夹")
        root.destroy()
        return folder_path
    except Exception as e:
        print(f"弹窗错误: {e}")
        return ""


def clean_path(path_str):
    if not path_str: return ""
    p = path_str.strip()
    if p.startswith('"') and p.endswith('"'): p = p[1:-1]
    if p.startswith("'") and p.endswith("'"): p = p[1:-1]
    return os.path.normpath(p)


def format_duration(seconds):
    if seconds is None: return "00:00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_video_info(file_path):
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None, "无法读取文件"

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = frame_count / fps if fps > 0 else 0
        cap.release()

        ext = os.path.splitext(file_path)[1].lower()
        ratio = width / height if height > 0 else 0

        check_format = ext == STANDARDS['format']
        check_fps = abs(fps - STANDARDS['target_fps']) <= STANDARDS['fps_tolerance']
        check_res = width >= STANDARDS['min_width'] and height >= STANDARDS['min_height']
        check_ratio = abs(ratio - STANDARDS['target_ratio']) <= STANDARDS['ratio_tolerance']
        is_passed = check_format and check_fps and check_res and check_ratio

        reasons = []
        if not check_format: reasons.append(f"格式错误({ext})")
        if not check_fps: reasons.append(f"帧率异常({round(fps, 2)})")
        if not check_res: reasons.append(f"分辨率不足({width}x{height})")
        if not check_ratio: reasons.append(f"比例错误({round(ratio, 2)})")

        return {
            "filename": os.path.basename(file_path),
            "width": width,
            "height": height,
            "fps": round(fps, 2),
            "duration_sec": duration_sec,
            "duration_str": format_duration(duration_sec),
            "format": ext,
            "passed": is_passed,
            "reason": " | ".join(reasons) if reasons else "合格"
        }, None
    except Exception as e:
        return None, str(e)


# 前端
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>视频质量检测系统</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <style>
        body { background-color: #f4f6f9; font-family: 'Microsoft YaHei', sans-serif; min-height: 100vh; display: flex; flex-direction: column; }
        .wrapper { flex: 1; display: flex; flex-direction: column; }
        .sidebar { min-height: 100vh; background: #212529; color: white; padding-top: 20px; }
        .sidebar a { color: rgba(255,255,255,.7); text-decoration: none; padding: 12px 20px; display: flex; align-items: center; }
        .sidebar a i { margin-right: 10px; font-size: 1.1rem; }
        .sidebar a:hover, .sidebar a.active { background: #2c3034; border-left: 3px solid #0d6efd; color: white; }
        .main-content { padding: 30px; flex: 1; }
        .card-custom { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); background: white; margin-bottom: 20px; }
        .spinner { display: none; width: 1rem; height: 1rem; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spinner-border .75s linear infinite; margin-right: 5px; }
        @keyframes spinner-border { to { transform: rotate(360deg); } }
        .footer-info { text-align: center; padding: 10px; color: #adb5bd; font-size: 0.85rem; margin-top: auto; border-top: 1px solid #e9ecef; background-color: #fff; width: 100%; }
        .login-icon-box { width: 80px; height: 80px; background: #e7f1ff; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; }
    </style>
</head>
<body>
<div class="wrapper">
{% if not session.get('user') %}
    <div class="container d-flex justify-content-center align-items-center" style="height: 90vh;">
        <div class="card card-custom p-5 shadow-lg" style="width: 450px;">
            <div class="text-center mb-5">
                <div class="login-icon-box"><i class="bi bi-camera-reels-fill" style="font-size: 2.5rem; color: #0d6efd;"></i></div>
                <h3 class="text-primary fw-bold">系统登录</h3>
            </div>
            <form method="POST" action="/login">
                <div class="mb-4">
                    <label class="form-label fw-bold">用户 ID</label>
                    <input type="text" name="username" class="form-control form-control-lg" placeholder=" 例如: ID001" required autofocus>
                </div>
                <button type="submit" class="btn btn-primary w-100 btn-lg">进入系统</button>
            </form>
        </div>
        <div class="text-center mt-3 text-muted small"><p>网页开发：XXX | 指导老师：XXXXXXX</p></div>
    </div>
{% else %}
    <div class="container-fluid p-0">
        <div class="row g-0">
            <div class="col-md-2 sidebar">
                <h5 class="text-center mb-4"><i class="bi bi-film"></i> 视频检测系统</h5>
                <div class="text-center mb-4 text-white-50 small">
                    <i class="bi bi-person-circle fs-4 mb-1 d-block text-white"></i> 当前用户: <span class="text-white">{{ session['user'] }}</span>
                </div>
                <a href="/" class="{% if not show_history %}active{% endif %}"><i class="bi bi-speedometer2"></i> 检测中心</a>
                <a href="/history" class="{% if show_history %}active{% endif %}"><i class="bi bi-clock-history"></i> 历史记录</a>
                <a href="/logout" class="text-danger mt-5"><i class="bi bi-box-arrow-right"></i> 退出登录</a>
            </div>
            <div class="col-md-10 d-flex flex-column" style="min-height: 100vh;">
                <div class="main-content">
                    {% if show_history %}
                        <div class="card card-custom p-4">
                            <h4><i class="bi bi-clock-history text-primary"></i> 历史记录</h4>
                            <table class="table table-hover mt-3">
                                <thead class="table-light"><tr><th>时间</th><th>用户</th><th>路径</th><th>合格/总数</th></tr></thead>
                                <tbody>
                                    {% for row in history_data %}
                                    <tr><td>{{ row.time }}</td><td>{{ row.user }}</td><td class="small">{{ row.path }}</td>
                                    <td><span class="fw-bold text-success">{{ row.pass_count }}</span> / {{ row.total }}</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    {% else %}
                        <div class="card card-custom p-4">
                            <label class="form-label fw-bold">选择目录</label>
                            <div class="input-group">
                                <button class="btn btn-secondary" onclick="browseFolder()">
                                    <span id="browseSpinner" class="spinner" style="display:none"></span> 📂浏览文件夹
                                </button>
                                <input type="text" id="folderPath" class="form-control" placeholder="请选择路径...">
                                <button class="btn btn-primary px-5 fw-bold" onclick="startScan()">
                                    <span id="scanSpinner" class="spinner" style="display:none"></span> <i class="bi bi-search"></i> 开始检测
                                </button>
                            </div>
                            <div class="mt-2" id="pathStatus"></div>
                        </div>
                        <div id="resultArea" style="display: none;" class="mt-4">
                            <div class="row text-center mb-3">
                                <div class="col-md-4"><h2 id="passCount" class="text-success fw-bold">0</h2><small>合格</small></div>
                                <div class="col-md-4"><h2 id="failCount" class="text-danger fw-bold">0</h2><small>不合格</small></div>
                                <div class="col-md-4"><h4 id="totalDuration">00:00:00</h4><small>总时长</small></div>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="card card-custom"><div class="card-header bg-danger text-white">❌ 不合格</div>
                                    <div class="card-body p-0 table-responsive" style="max-height:400px"><table class="table table-striped small"><tbody id="failTableBody"></tbody></table></div></div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card card-custom"><div class="card-header bg-success text-white">✅ 合格</div>
                                    <div class="card-body p-0 table-responsive" style="max-height:400px"><table class="table table-striped small"><tbody id="passTableBody"></tbody></table></div></div>
                                </div>
                            </div>
                        </div>
                    {% endif %}
                </div>
                <div class="footer-info"><p class="mb-0">网页开发：XXX | 指导老师：XXXXXXX</p></div>
            </div>
        </div>
    </div>
{% endif %}
</div>
<div class="modal fade" id="namingErrorModal" tabindex="-1"><div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content"><div class="modal-body text-center"><h4 class="text-danger">命名或结构错误</h4><img src="/static/structure_guide.png" class="img-fluid" style="max-height:300px"><br><button class="btn btn-primary mt-3" data-bs-dismiss="modal">好的</button></div></div></div></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
    function browseFolder() {
        document.getElementById('browseSpinner').style.display = 'inline-block';
        fetch('/api/browse_folder').then(r=>r.json()).then(d=>{
            document.getElementById('browseSpinner').style.display='none';
            if(d.path) document.getElementById('folderPath').value=d.path;
        });
    }
    function startScan() {
        const path = document.getElementById('folderPath').value;
        if(!path) return alert("请选择文件夹");
        document.getElementById('scanSpinner').style.display='inline-block';
        document.getElementById('resultArea').style.display='none';
        document.getElementById('pathStatus').innerHTML='正在扫描...';
        fetch('/api/scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:path})})
        .then(r=>r.json()).then(d=>{
            document.getElementById('scanSpinner').style.display='none';
            if(d.structure_error) { new bootstrap.Modal(document.getElementById('namingErrorModal')).show(); return; }
            if(d.error) { document.getElementById('pathStatus').innerHTML=d.error; return; }
            document.getElementById('pathStatus').innerHTML='检测完成';
            document.getElementById('resultArea').style.display='block';
            document.getElementById('passCount').innerText=d.results.filter(x=>x.passed).length;
            document.getElementById('failCount').innerText=d.results.filter(x=>!x.passed).length;
            document.getElementById('totalDuration').innerText=d.total_duration;
            document.getElementById('passTableBody').innerHTML = d.results.filter(x=>x.passed).map(x=>`<tr><td>${x.filename}</td><td>${x.duration_str}</td></tr>`).join('');
            document.getElementById('failTableBody').innerHTML = d.results.filter(x=>!x.passed).map(x=>`<tr><td>${x.filename}</td><td class="text-danger">${x.reason}</td></tr>`).join('');
        });
    }
</script>
</body>
</html>
"""


# 路由
@app.route('/', methods=['GET', 'POST'])
def index(): return render_template_string(HTML_TEMPLATE, show_history=False)


@app.route('/login', methods=['POST'])
def login():
    if request.form.get('username'): session['user'] = request.form.get('username'); return redirect('/')
    return render_template_string(HTML_TEMPLATE, error="ID 不能为空")


@app.route('/logout')
def logout(): session.clear(); return redirect('/')


@app.route('/history')
def history():
    if not session.get('user'): return redirect('/')
    u_data = [d for d in load_history() if d['user'] == session['user']]
    return render_template_string(HTML_TEMPLATE, show_history=True, history_data=reversed(u_data))


@app.route('/api/browse_folder')
def api_browse_folder():
    path = open_folder_dialog();
    return jsonify({'path': path.replace('\\', '/') if path else ''})


@app.route('/api/scan', methods=['POST'])
def api_scan():
    if not session.get('user'): return jsonify({'error': '未登录'}), 401
    path = clean_path(request.json.get('path', ''))
    if not path or not os.path.exists(path): return jsonify({'error': '路径不存在'}), 400

    results = []
    ptrn = re.compile(r"^(.+)-(\d{6})-(\d{2})\.(mp4|mov|avi|mkv)$", re.IGNORECASE)
    found = False
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                found = True
                m = ptrn.match(f)
                if not m: return jsonify({'structure_error': True})
                if os.path.basename(root) != f"{m.group(1)}-{m.group(2)}": return jsonify({'structure_error': True})
                info, err = get_video_info(os.path.join(root, f))
                if info: results.append(info)

    if not found: return jsonify({'error': '未找到视频'}), 404

    total_sec = sum(r['duration_sec'] for r in results)
    save_history_record(
        {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "user": session['user'], "path": path,
         "pass_count": sum(1 for r in results if r['passed']), "total": len(results)})

    return jsonify({
        'results': results,
        'total_duration': format_duration(total_sec),
        'valid_duration': format_duration(sum(r['duration_sec'] for r in results if r['passed'])),
        'invalid_duration': format_duration(sum(r['duration_sec'] for r in results if not r['passed']))
    })


# 启动
def open_browser(port):
    webbrowser.open_new(f'http://127.0.0.1:{port}/')


if __name__ == '__main__':
    # Nuitka 打包
    port = find_free_port(5555)
    print(f"系统启动中... http://127.0.0.1:{port}")

    if not os.path.exists('static'): os.makedirs('static')

    Timer(1.5, open_browser, [port]).start()
    app.run(host='0.0.0.0', port=port, debug=False)
