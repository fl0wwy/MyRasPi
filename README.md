# 🖥️ Raspberry Pi Status Dashboard

A sleek, dark-themed web dashboard for monitoring your Raspberry Pi (or any Linux system) — built with **Django**, **psutil**, and **Raspberry Pi-specific metrics** such as power, temperature, and Wi-Fi strength.

![screenshot](./example.png)

---

## ✨ Features

- 🧠 Live CPU, RAM, Disk, and Network usage  
- ⚡ Power-supply & temperature monitoring (`vcgencmd`)  
- 📶 Auto-detects Ethernet / Wi-Fi connection  
- ⏱ Router + Internet ping latency  
- 💾 Disk I/O + free-space color warnings  
- 🧩 Top processes by CPU / RAM  
- 🌐 Optional Cloudflare Tunnel for secure remote access  
- 🕶 Polished Raspberry-pink dark-mode UI  

---

## 🧱 System Requirements

| Component | Minimum |
|:-----------|:---------|
| OS | Raspberry Pi OS (Bookworm) / Ubuntu 22+ |
| Python | 3.11+ |
| Packages | `libraspberrypi-bin`, `wireless-tools`, `iputils-ping`, `git` |
| Network | Internet optional (for ping / Cloudflare) |

### Install dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git \
  libraspberrypi-bin wireless-tools iputils-ping
```


## 🖥️ Installation & Running

```bash
# 1️⃣ Clone
git clone https://github.com/fl0wwy/MyRasPi.git
cd raspi-status

# 2️⃣ Create virtual environment
python3 -m venv env

# 3️⃣ Activate it
source env/bin/activate     # (Linux / macOS)
# env\Scripts\activate       # (Windows)

# 4️⃣ Install dependencies
pip install -r requirements.txt

# 5️⃣ Launch the dashboard
./run.sh  
```
### Then open your browser at http://"your-pi-ip":8123
To change the port:
```bash
PORT=your-port ./run.sh
```

## 🧾 Project Structure
```bash
raspi-status/
├── env/                    # virtual environment
├── run.sh                  # launcher script
├── requirements.txt
├── statuspi/
    ├── manage.py
    ├── statuspi/           # Django settings
    └── statuspiweb/        # templates, static, and views    
        ├── metrics.py      # system metric functions   
```

## 📜 License

MIT License © 2025 Bar Ben Waiss
Free to use, modify, and self-host.

## ❤️ Credits

Built by Bar Ben Waiss

Designed for Raspberry Pi enthusiasts and tinkerers.
