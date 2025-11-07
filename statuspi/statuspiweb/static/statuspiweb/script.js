const SECTIONS = document.querySelectorAll('.section')
const ICONS = document.querySelectorAll('.icon')
const select = document.getElementById('refreshrate')
const unit = document.getElementById('tempUnit')

select.value = localStorage.getItem('refresh') ?? '3000'
unit.value = localStorage.getItem('unit') ?? 'C'

async function loadMetrics() {
  try {
    const r = await fetch("/metrics", { cache: "no-store" });
    const m = await r.json();
    render(m);
    document.getElementById("refresh").textContent = m.timestamp;
  } catch (e) {
    console.error("metrics fetch failed", e);
  }
}

function render(m) {

  function getTemp(unit){
    localStorage.setItem('unit', unit)
    
    if (unit === 'C') {
      return m.temp_c  
    }
    else {
      return (parseFloat(m.temp_c) * 1.8 + 32).toFixed(1)
    }
  }

  setText("#cpu-usage", `${m.cpu.usage.toFixed(1)}%`);
  setText("#temp", (getTemp(unit.value) ?? "–") + ` °${unit.value}`);
  setText("#wifi", (m.wifi?.signal_pct ?? "–") + "%");
  setText("#uptime", m.uptime);
  setText("#per_core", m.cpu.per_core);
  setText("#freq", m.cpu.freq.toFixed(1) + " GHz");
  setText("#load_avg", m.cpu.load_avg);
  setText("#net-up",  m.network.up_human ?? "-");
  setText("#net-dn",  m.network.dn_human ?? "-");
  
  
  setText("#pingI",  (m.internet_ms ?? "–") + "ms");
  document.getElementById('pingI').style.color = m.internet_ms > 100 ? "#ff4d6d" : m.internet_ms >= 20 ? "#ffd34e" : "#3fd97f"
  
  setText("#pingR",  (m.router_ms ?? "–") + "ms");
  document.getElementById('pingR').style.color = m.router_ms > 15 ? "#ff4d6d" : m.router_ms >= 5 ? "#ffd34e" : "#3fd97f"

  const tempColor=
    m.temp_c > 85 ? "#ff4d6d" :
    m.temp_c > 70 ? "#ffd34e" : "#3fd97f";
  document.documentElement.style.setProperty("--temp-color", tempColor);

  setText("#smem", `${m.memory.swap.used_human} / ${m.memory.swap.total_human} (${m.memory.swap.percent}%)`);
  const smemPct = m.memory.swap.percent
  document.getElementById('smem').style.color = smemPct >= 60 ? "#ff4d6d" : smemPct >= 20 ? "#ffd34e" : smemPct === 0 ? "grey" : "#3fd97f";
  
  setText("#mem", `${m.memory.used_human} / ${m.memory.total_human} (${m.memory.percent}%) - ${m.memory.available_human} free`);
  const bar = document.querySelector("#mem-bar .fill");
  if (bar) {
    const pct = m.memory.percent || 0;
    bar.style.width = pct + "%";
    bar.style.background = pct >= 85 ? "#ff4d6d" : pct >= 70 ? "#ffd34e" : "#3fd97f";
  }

  const disks = document.querySelectorAll(".disk")
  disks.forEach((disk, i) => {
      const mdisk = m.disks[i]
      disk.id = diskIdFromMount(mdisk.mount)

      document.querySelectorAll(`#${disk.id} p`).forEach(p => {
        if (!p.id.includes(disk.id)) {
            p.id = `${disk.id}${p.id.charAt(0).toUpperCase()}`
        }
      })
      
      setText(`${disk.id}S`, `${ mdisk.used_human } / ${ mdisk.total_human } (${ mdisk.percent }%) - ${ mdisk.free_human} free`)
      setText(`${disk.id}R`, mdisk.read_rate)
      setText(`${disk.id}W`, mdisk.write_rate)

      const diskBar = document.querySelector(`#${disk.id} .fill`)
      if (diskBar) {
        const pct = mdisk.percent || 0;
        diskBar.style.width = pct + "%";
        diskBar.style.background = pct >= 90 ? "#ff4d6d" : pct >= 75 ? "#ffd34e" : "#3fd97f";
      }
  });

  const powerCard = document.getElementById('power')
  setText("#power-message",  m.power.status.message + ` (${m.power.flags.raw})`);
  if (m.power.status.level === 'ok') {
    powerCard.style.color = "#3fd97f"
  }
  else if (m.power.status.level === 'warn') {
    powerCard.style.color = "#ffd34e"
  }
  else if (m.power.status.level === 'bad') {
    powerCard.style.color = "#ff4d6d"
  }

  const processTable = document.querySelector('#processes table')
  processTable.innerHTML = '<tr><th>Name</th><th>CPU</th><th>Memory</th><th>Read</th><th>Write</th></tr>'
  for (let i = 0; i < m.processes.length; i++) {
    const process = m.processes[i];
    
    const row = document.createElement("tr")
    row.className = 'process'
    row.id = process.name + process.pid
    processTable.appendChild(row)

    row.setAttribute('marked', localStorage.getItem(row.id) ?? false)
    if (row.getAttribute('marked') === 'true') {
      row.style.backgroundColor = "#8f0e32"
    }
    
    row.addEventListener('click', () => {
      if (!row.marked) {
        row.marked = true
        localStorage.setItem(row.id, true)
        
        row.style.backgroundColor = "#8f0e32"

        document.querySelectorAll('.process').forEach(proc => {
          if (proc != row) {
            proc.marked = false
            localStorage.setItem(proc.id, false)

            proc.style.backgroundColor = 'transparent'
          }
        })
      }
      else{
        row.style.backgroundColor = 'transparent'
        
        row.marked = false
        localStorage.setItem(row.id, false)
      }
    })

    const name = document.createElement("td")
    name.className = 'name'
    name.textContent = process.name
    
    const cpu_pct = document.createElement("td")
    cpu_pct.textContent = process.cpu_pct + '%'

    const mem_pct = document.createElement("td")
    mem_pct.textContent = process.mem_pct + '%'

    const read_bytes = document.createElement("td")
    read_bytes.textContent = process.read_bytes

    const write_bytes = document.createElement("td")
    write_bytes.textContent = process.write_bytes 

    row.appendChild(name)
    row.appendChild(cpu_pct)
    row.appendChild(mem_pct)
    row.appendChild(read_bytes)
    row.appendChild(write_bytes)
  }
}

function setText(sel, txt){ const el=document.querySelector(sel); if(el) el.textContent=txt; }

loadMetrics();

let timer;
function setRate(val) {
  clearInterval(timer);
  timer = setInterval(loadMetrics, val);
}
select.addEventListener("change", () => {
  setRate(parseFloat(select.value))
  localStorage.setItem('refresh', select.value)
});
setRate(parseFloat(select.value)); // initial

function diskIdFromMount(mount) {
  if (mount === "/") return "disk-root";
  // remove leading/trailing slashes
  let id = mount.replace(/^\/+|\/+$/g, "");
  // replace remaining slashes with underscores
  id = id.replace(/\//g, "_");
  // replace spaces or weird chars with underscores
  id = id.replace(/[^a-zA-Z0-9_-]/g, "_");
  // prefix with "disk-" so IDs never start with a number
  return "disk-" + id;
}

ICONS.forEach(icon => {
    icon.id === 'health' ? icon.setAttribute('active', true) : icon.setAttribute('active', false)

    icon.addEventListener('click', () => {
        ICONS.forEach(otherIcon => {
            if (otherIcon != icon) {
                otherIcon.active = false
            }
        })

        icon.active = true
        SECTIONS.forEach(section => {
            if (section.id === icon.id) {
                section.style.display = 'flex'
            }
            else {
                section.style.display = 'none'
            }
        })

    })
});
