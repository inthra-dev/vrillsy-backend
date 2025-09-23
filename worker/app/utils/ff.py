import json, subprocess, shlex

def run(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode("utf-8", "ignore"), p.stderr.decode("utf-8", "ignore")

def ffprobe_json(path):
    cmd = f'ffprobe -v error -print_format json -show_format -show_streams {shlex.quote(path)}'
    code, out, err = run(cmd)
    if code != 0:
        raise RuntimeError(f"ffprobe_error:{err.strip()[:4000]}")
    return json.loads(out)

def get_rotation(stream):
    try:
        tags = stream.get("tags", {}) or {}
        r = tags.get("rotate")
        if r is None:
            r = stream.get("side_data_list", [{}])[0].get("rotation")
        if r is None:
            return 0
        r = int(float(r))
        r = r % 360
        return r
    except Exception:
        return 0
