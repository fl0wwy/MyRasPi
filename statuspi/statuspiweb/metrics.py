import psutil, time, os, platform, socket, subprocess, sys, requests, re, shutil
from datetime import datetime
from dataclasses import dataclass
from math import ceil

# Driver inclusion settings
SKIP_FS = {"tmpfs", "devtmpfs", "squashfs", "overlay"}
SKIP_MOUNT_PREFIX = ("/snap", "/proc", "/sys", "/run", "/dev", "/boot")  # /boot optional

@dataclass
class _NetState:
    ts: float
    sent: int
    recv: int
    up_bps: float = 0.0
    dn_bps: float = 0.0

_state = None
_ALPHA = 0.35  # EMA smoothing: 0=no smooth, 1=aggressive (keep ~0.25–0.5)

def get_net_totals_and_rates():
    """
    Returns totals since boot (bytes) and smoothed rates (bytes/sec).
    Call at ~1–2s cadence (your sampler/SSE tick).
    """
    global _state
    now = time.time()
    io = psutil.net_io_counters(pernic=False)  # totals across all NICs

    if _state is None:
        _state = _NetState(ts=now, sent=io.bytes_sent, recv=io.bytes_recv)
        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "up_bps": 0.0,
            "dn_bps": 0.0,
        }

    dt = max(0.001, now - _state.ts)
    d_sent = max(0, io.bytes_sent - _state.sent)  # guard against counter reset
    d_recv = max(0, io.bytes_recv - _state.recv)

    inst_up = d_sent / dt  # bytes/sec
    inst_dn = d_recv / dt

    # EMA smoothing
    up = _ALPHA * inst_up + (1 - _ALPHA) * _state.up_bps
    dn = _ALPHA * inst_dn + (1 - _ALPHA) * _state.dn_bps

    _state = _NetState(ts=now, sent=io.bytes_sent, recv=io.bytes_recv,
                       up_bps=up, dn_bps=dn)

    return {
        "bytes_sent": io.bytes_sent,
        "bytes_recv": io.bytes_recv,
        "up_bps": up,
        "dn_bps": dn,
    }

def bps_to_human(n: float) -> str:
    # bytes/sec → human; keep bytes, KB/s, MB/s, GB/s
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    for u in units:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB/s"

_ping_re = re.compile(r'time[=<]([\d\.]+)\s*ms')

def get_lan_ip():
    """
    Attempts to retrieve the local LAN IP address of the machine.
    Returns the IP address as a string, or None if it cannot be determined.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception:
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            # Filter out loopback address if returned
            if ip_address == "127.0.0.1":
                return None 
            return ip_address
        except Exception:
            return None

def get_router_ip():
    """
    Detect the default gateway (router) IP from the system routing table.
    Works on Linux with 'ip route' or 'ip r'.
    """
    try:
        out = subprocess.check_output(["ip", "route"], text=True)
        # Example line: 'default via 192.168.1.1 dev wlan0 proto dhcp metric 600'
        m = re.search(r"default\s+via\s+([\d\.]+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

def ping_ms(host=get_router_ip(), timeout=2):
    """Pings an IP address to check latency
    """
    try:
        out = subprocess.check_output(
            ["ping", "-c", "1", "-w", str(timeout), host],
            stderr=subprocess.STDOUT,
            text=True
        )
        m = _ping_re.search(out)
        return float(m.group(1)) if m else None
    except subprocess.CalledProcessError:
        return None

def get_active_network():
    """Retrieves network connection type

    Returns:
        Dict: Network connection data
    """
    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    active = []

    for name, addrs in interfaces.items():
        if name not in stats or not stats[name].isup:
            continue  # skip inactive

        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address != "127.0.0.1":
                active.append({
                    "name": name,
                    "ip": addr.address,
                    "speed": stats[name].speed,  # may be 0 if unknown
                    "mtu": stats[name].mtu,
                })

    # Decide which to use as primary
    if not active:
        return {"type": "none", "iface": None, "ip": None}

    # Heuristic: prefer eth0 > wlan0 > anything else
    preferred = sorted(active, key=lambda x: ("eth" not in x["name"], "wlan" not in x["name"]))
    primary = preferred[0]

    # Determine type
    if primary["name"].startswith("eth"):
        net_type = "Ethernet"
    elif primary["name"].startswith("wlan"):
        net_type = "Wi-Fi"
    else:
        net_type = "Other"

    return {
        "type": net_type,
        "iface": primary["name"],
        "ip": primary["ip"],
        "speed": primary["speed"],
        "mtu": primary["mtu"]
    }

def wifi_info():
    """
    Returns dict with ssid, rssi_dbm (negative), signal_pct (0-100), bitrate_mbps (optional).
    """
    # 1) nmcli (best: already gives percent)
    if shutil.which("nmcli"):
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "active,ssid,signal", "dev", "wifi"],
                text=True
            )
            for line in out.splitlines():
                if line.startswith("yes:"):
                    _, ssid, pct = line.split(":", 2)
                    pct = int(pct) if pct.isdigit() else None
                    return {"ssid": ssid or None, "signal_pct": pct, "rssi_dbm": None, "bitrate_mbps": None}
        except Exception:
            pass

    # 2) iw dev wlan0 link
    if shutil.which("iw"):
        try:
            out = subprocess.check_output(["iw", "dev", "wlan0", "link"], text=True)
            ssid = None; rssi = None; rate = None
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("SSID:"):
                    ssid = line.split("SSID:",1)[1].strip() or None
                elif line.startswith("signal:"):
                    # e.g. signal: -54 dBm
                    m = re.search(r"(-?\d+)\s*dBm", line)
                    if m: rssi = int(m.group(1))
                elif line.startswith("tx bitrate:"):
                    m = re.search(r"([\d\.]+)\s*MBit/s", line)
                    if m: rate = float(m.group(1))
            pct = rssi_to_percent(rssi) if rssi is not None else None
            return {"ssid": ssid, "rssi_dbm": rssi, "signal_pct": pct, "bitrate_mbps": rate}
        except Exception:
            pass

    # 3) iwconfig wlan0
    if shutil.which("iwconfig"):
        try:
            out = subprocess.check_output(["iwconfig", "wlan0"], text=True, stderr=subprocess.STDOUT)
            ssid = None; rssi = None; pct = None
            m = re.search(r'ESSID:"([^"]*)"', out)
            if m: ssid = m.group(1)
            m = re.search(r"Signal level=([-]?\d+)\s*dBm", out)
            if m: rssi = int(m.group(1))
            # sometimes prints Link Quality=40/70
            m = re.search(r"Link Quality=(\d+)/(\d+)", out)
            if m:
                num, den = int(m.group(1)), int(m.group(2))
                pct = int(round((num/den)*100))
            else:
                pct = rssi_to_percent(rssi) if rssi is not None else None
            return {"ssid": ssid, "rssi_dbm": rssi, "signal_pct": pct, "bitrate_mbps": None}
        except Exception:
            pass

    return {"ssid": None, "rssi_dbm": None, "signal_pct": None, "bitrate_mbps": None}

def rssi_to_percent(rssi_dbm):
    """
    Rough mapping of RSSI (dBm) to a 0–100% "bars" scale.
    -30 dBm ~ 100% (excellent), -67 ~ 70% (good), -80 ~ 30% (poor), -90 ~ 10%.
    """
    if rssi_dbm is None:
        return None
    # clamp and scale between -90..-30
    rssi_dbm = max(-90, min(-30, rssi_dbm))
    return int(round((rssi_dbm + 90) * (100/60.0)))    

def get_temp_c():
    """Retrieves vcgencmd cpu/gpu temp
    """
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True).strip()
        if out.startswith("temp=") and out.endswith("'C"):
            return float(out[5:-2])
    except Exception:
        pass
    return None

def uptime_to_human(seconds: int) -> str:
    """
    Convert uptime in seconds into a human-readable string like:
    '3d 4h 12m', '5h 2m 9s', or '1y 23d 6h'
    """
    if seconds < 0:
        return "0s"

    minute = 60
    hour = 60 * minute
    day = 24 * hour
    year = 365 * day

    years, rem = divmod(seconds, year)
    days, rem = divmod(rem, day)
    hours, rem = divmod(rem, hour)
    minutes, secs = divmod(rem, minute)

    parts = []
    if years:
        parts.append(f"{years}y")
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts or secs:  # always show seconds if nothing else
        parts.append(f"{secs}s")

    return " ".join(parts)


def bytes_to_human(n: int) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def normalize_dev_name(device_path):
    """Helper function that turns device name from psutil.disk_partitions
    to perdisk format in psutil.disk_io_counters
    """
    if not device_path.startswith("/dev/"):
        return None
    name = device_path.split("/dev/")[1]
    # remove partition suffix: e.g. mmcblk0p2 -> mmcblk0
    if name.startswith("mmcblk") and "p" in name:
        name = name.split("p")[0]
    elif name[-1].isdigit():
        name = "".join([c for c in name if not c.isdigit()])
    return name

def get_disks_info():
    """Return a list of real mounted filesystems with usage stats."""
    disks = []
    seen = set()

    aio = psutil.disk_io_counters(perdisk=True)       
    t1 = time.time()
    
    time.sleep(1)
    
    bio = psutil.disk_io_counters(perdisk=True)
    t2 = time.time()
    
    dt = t2 - t1

    for part in psutil.disk_partitions(all=False):
        if part.fstype in SKIP_FS:
            continue
        if part.mountpoint.startswith(SKIP_MOUNT_PREFIX):
            continue
        # avoid duplicate device entries
        key = (part.device, part.mountpoint)
        if key in seen:
            continue
        seen.add(key)

        try:
            usage = psutil.disk_usage(part.mountpoint)
            
            if normalize_dev_name(part.device) in bio and normalize_dev_name(part.device) in aio:
                read_rate  = (bio[normalize_dev_name(part.device)].read_bytes  - aio[normalize_dev_name(part.device)].read_bytes) / dt
                write_rate = (bio[normalize_dev_name(part.device)].write_bytes - aio[normalize_dev_name(part.device)].write_bytes) / dt 
            else:
                read_rate = write_rate = None    
            
        except PermissionError:
            continue

        disks.append({
            "device": part.device,
            "mount": part.mountpoint,
            "fstype": part.fstype or None,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.percent, 1),
            'read_rate': f"{read_rate/1024:.1f} KB/s",
            'write_rate': f"{write_rate/1024:.1f} KB/s",

            # human-friendly
            "total_human": bytes_to_human(usage.total),
            "used_human":  bytes_to_human(usage.used),
            "free_human":  bytes_to_human(usage.free),
        })

    # sort: root first, then others by mount path
    disks.sort(key=lambda d: (d["mount"] != "/", d["mount"]))
    return disks

def get_memory_info():
    """Retrieves memory info

    Returns:
        Dict: Memory data
    """
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    return {
        "total": vm.total,
        "used": vm.used,            # note: on Linux "used" includes cache; "available" is more meaningful
        "available": vm.available,
        "percent": round(vm.percent, 1),
        "total_human": bytes_to_human(vm.total),
        "used_human": bytes_to_human(vm.used),
        "available_human": bytes_to_human(vm.available),
        "swap": {
            "total": sm.total,
            "used": sm.used,
            "percent": round(sm.percent, 1),
            "total_human": bytes_to_human(sm.total),
            "used_human": bytes_to_human(sm.used),
        },
    }

def get_power_flags():
    """
    Returns decoded flags from `vcgencmd get_throttled`.
    On non-Pi or if vcgencmd is missing, return None.
    """
    try:
        out = subprocess.check_output(
            ["vcgencmd", "get_throttled"], text=True
        ).strip()
        # example: 'throttled=0x0' or 'throttled=0x50005'
        val = int(out.split("=")[1], 0)
    except Exception:
        return None

    return {
        "raw": hex(val),
        "undervoltage": bool(val & (1 << 0)),
        "freq_capped": bool(val & (1 << 1)),
        "throttled": bool(val & (1 << 2)),
        "undervoltage_history": bool(val & (1 << 16)),
        "freq_capped_history": bool(val & (1 << 17)),
        "throttled_history": bool(val & (1 << 18)),
    }

def power_status_from_flags(flags):
    """Decodes the flags from get_power_flags to readable messages

    Args:
        flags (Dict): get_power_flags

    Returns:
        Dict: Level and message decoded from flags
    """
    if flags is None:
        return {
            "level": "unknown",
            "message": "Power info not available",
        }

    # current bad > historical warning > ok
    if flags["undervoltage"] or flags["throttled"]:
        return {
            "level": "bad",
            "message": "Undervoltage / throttled NOW — check PSU or cable",
        }

    if (flags["undervoltage_history"] or
        flags["throttled_history"] or
        flags["freq_capped"] or
        flags["freq_capped_history"]):
        return {
            "level": "warn",
            "message": "Power issue occurred in the past",
        }

    return {
        "level": "ok",
        "message": "Power OK",
    }

def get_top_processes():
    """Return a list of all processes 

    Returns:
        List: List of all processes 
    """
    procs = []

    for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent"]):
        try:
            pid = p.info["pid"]
            name = p.info["name"]

            mem_pct = p.memory_percent()

            # per-process disk I/O can also raise AccessDenied
            try:
                io = p.io_counters()
                rbytes = io.read_bytes
                wbytes = io.write_bytes
            except (psutil.AccessDenied, AttributeError):
                rbytes = wbytes = 0

            # if float(p.info['cpu_percent']) == 0 and float(mem_pct) == 0 and float(rbytes) == 0 and float(wbytes) == 0:
            #     continue     

            procs.append({ 
                "pid": pid,
                "name": name,
                "cpu_pct": p.info['cpu_percent'],
                "mem_pct": round(mem_pct, 2),
                "read_bytes": bytes_to_human(rbytes),
                "write_bytes": bytes_to_human(wbytes),
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # just skip system/root processes we can't read
            continue

    procs.sort(key=lambda x: (x["cpu_pct"], x["mem_pct"], x["read_bytes"], x["write_bytes"]), reverse=True)
    return procs

def get_metrics():
    """Returns the dictionary of all the parameters

    Returns:
        Dictionary: The dictionary of all the parameters
    """
    load1, load5, load15 = psutil.getloadavg()
    net = get_net_totals_and_rates()
    disks  = get_disks_info()
    memory = get_memory_info()
    connection = get_active_network()

    power_flags = get_power_flags()
    power_status = power_status_from_flags(power_flags)

    with open("/proc/device-tree/model", "r") as f:
        model = f.read().strip()

    return {
        "timestamp": datetime.now().strftime("%d/%m/%Y, %H:%M:%S"),
        
        "cpu": {
            "usage": psutil.cpu_percent(),
            "per_core": '%, '.join(map(lambda x: str(x) ,psutil.cpu_percent(percpu=True))) + "%",
            "load_avg": f'({round(load1, 3)}, {round(load5, 3)}, {round(load15, 3)}) / {os.cpu_count()} cores',
            "freq": psutil.cpu_freq().current / 1000 if psutil.cpu_freq() else None,
        },
        'temp_c': get_temp_c(),
        "memory": memory,
        "disks": [disk for disk in disks],
        "power": {
            "flags": power_flags,   # raw + booleans
            "status": power_status, # level + message
        },
        "uptime": uptime_to_human(int(time.time() - psutil.boot_time())),

        "processes": get_top_processes(),
        
        "network": {
            "bytes_sent": net["bytes_sent"],
            "bytes_recv": net["bytes_recv"],
            "up_bps": net["up_bps"],
            "dn_bps": net["dn_bps"],
            "up_human": bps_to_human(net["up_bps"]),
            "dn_human": bps_to_human(net["dn_bps"]),
        },
        "int_ip": get_lan_ip(),
        "ext_ip": str(requests.get('https://api.ipify.org/').content)[1:].strip("'"),
        "internet_ms": ping_ms("8.8.8.8"),
        "router_ms": ping_ms(),
        "connection": connection,
        "wifi": wifi_info() if connection["type"] == "Wi-Fi" else None,
        
        "model": f'{model} ({ceil(float(memory['total_human'].strip('GB')))}GB RAM)',
        "hostname": platform.node(),
        "os": os.uname().sysname,
        "kernel": os.uname().release,
        "python_version": sys.version,
        "architecture": platform.machine(),
    }