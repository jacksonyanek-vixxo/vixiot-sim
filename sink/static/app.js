const DOMAIN_FAULTS = ["scaling", "grinder_wear", "pump_degradation", "clogged_group", "heater_degradation"];
const GENERIC_FAULTS = ["spike", "drift", "stuck", "dropout", "out_of_range", "noise"];
const FAULTS = [...DOMAIN_FAULTS, ...GENERIC_FAULTS];
const QUALITY_COLORS = { good: "#2dd4bf", suspect: "#f59e0b", bad: "#ef4444", missing: "#64748b" };

function initialFaults() {
  return Object.fromEntries(FAULTS.map(name => [name, {
    enabled: false,
    severity: 0.5,
    [DOMAIN_FAULTS.includes(name) ? "mtbf_hours" : "rate_per_hour"]: DOMAIN_FAULTS.includes(name) ? 200 : 1,
  }]));
}

document.addEventListener("alpine:init", () => {
  Alpine.data("dashboard", () => ({
    devices: [],
    selectedId: "",
    snapshot: {},
    history: [],
    workorders: { open: [], closed: [] },
    config: { sample_interval_ms: 1000, publish_interval_s: 30, irregularities: initialFaults() },
    faultNames: FAULTS,
    charts: {},
    socket: null,
    reconnectTimer: null,
    lastAck: null,
    error: "",
    notice: "",
    saving: false,

    async init() {
      await new Promise(resolve => setTimeout(resolve, 0));
      this.createCharts();
      await this.loadDevices();
      this.connectSocket();
    },

    async request(url, options) {
      const response = await fetch(url, options);
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      return response.json();
    },

    async loadDevices() {
      try {
        this.devices = await this.request("/api/devices");
        if (!this.selectedId && this.devices.length) {
          this.selectedId = this.devices[0].device_id;
          await this.selectDevice();
        }
      } catch (error) {
        this.error = `Backend unavailable: ${error.message}`;
      }
    },

    async selectDevice() {
      if (!this.selectedId) return;
      try {
        const id = encodeURIComponent(this.selectedId);
        const [snapshot, history, workorders] = await Promise.all([
          this.request(`/api/snapshot/${id}`),
          this.request(`/api/telemetry/${id}`),
          this.request(`/api/workorders/${id}`),
        ]);
        this.snapshot = snapshot;
        this.history = history;
        this.workorders = workorders;
        this.lastAck = snapshot.cmd_ack;
        this.loadConfig(snapshot.config);
        this.refreshCharts();
        this.error = "";
      } catch (error) {
        this.error = error.message;
      }
    },

    connectSocket() {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      this.socket = new WebSocket(`${protocol}://${location.host}/ws`);
      this.socket.onmessage = event => this.handleEvent(JSON.parse(event.data));
      this.socket.onopen = () => { this.error = ""; };
      this.socket.onerror = () => { this.error = "Live connection interrupted"; };
      this.socket.onclose = () => {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => this.connectSocket(), 2000);
      };
    },

    handleEvent(event) {
      if (event.type === "backfill") {
        this.devices = Object.keys(event.devices).sort().map(device_id => ({
          device_id,
          online: Boolean(event.devices[device_id].snapshot?.online),
        }));
        if (!this.selectedId && this.devices.length) {
          this.selectedId = this.devices[0].device_id;
        }
        const data = event.devices[this.selectedId];
        if (data) {
          this.snapshot = data.snapshot || {};
          this.history = data.telemetry || [];
          this.workorders = data.workorders || { open: [], closed: [] };
          this.loadConfig(this.snapshot.config);
          this.refreshCharts();
        }
        return;
      }
      this.upsertDevice(event.device_id);
      if (event.device_id !== this.selectedId) return;
      if (event.type === "telemetry") {
        this.snapshot = { ...this.snapshot, ...event.data };
        this.history.push(event.data);
        this.history = this.history.slice(-500);
        this.refreshCharts();
      } else if (event.type === "state") {
        this.snapshot.online = event.data.status === "online";
        this.snapshot.connection_status = event.data.status;
      } else if (event.type === "workorder") {
        this.updateWorkorder(event.data);
      } else if (event.type === "cmd_ack") {
        this.lastAck = event.data;
        this.notice = event.data.success ? "Configuration applied by device" : "";
        if (!event.data.success) this.error = event.data.message || "Device rejected configuration";
      }
    },

    upsertDevice(deviceId) {
      if (!this.devices.some(device => device.device_id === deviceId)) {
        this.devices.push({ device_id: deviceId, online: false });
      }
      if (!this.selectedId) {
        this.selectedId = deviceId;
        this.selectDevice();
      }
    },

    updateWorkorder(order) {
      this.workorders.open = this.workorders.open.filter(item => item.wo_id !== order.wo_id);
      if (order.status === "open") this.workorders.open.unshift(order);
      else {
        this.workorders.closed = this.workorders.closed.filter(item => item.wo_id !== order.wo_id);
        this.workorders.closed.unshift(order);
      }
    },

    loadConfig(applied) {
      if (!applied) return;
      const merged = initialFaults();
      for (const name of FAULTS) Object.assign(merged[name], applied.irregularities?.[name] || {});
      this.config = {
        sample_interval_ms: applied.sample_interval_ms ?? 1000,
        publish_interval_s: applied.publish_interval_s ?? 30,
        irregularities: merged,
      };
    },

    async applyConfig() {
      this.saving = true;
      this.error = "";
      this.notice = "";
      try {
        await this.request(`/api/config/${encodeURIComponent(this.selectedId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.config),
        });
        this.notice = "Configuration command sent; awaiting device acknowledgement";
      } catch (error) {
        this.error = error.message;
      } finally {
        this.saving = false;
      }
    },

    healthyPreset() {
      this.config.sample_interval_ms = 1000;
      this.config.publish_interval_s = 30;
      for (const name of FAULTS) this.config.irregularities[name].enabled = false;
    },

    aggressivePreset() {
      this.config.sample_interval_ms = 100;
      this.config.publish_interval_s = 5;
      for (const name of FAULTS) {
        const item = this.config.irregularities[name];
        item.enabled = true;
        item.severity = 1;
        item[this.rateKey(name)] = this.isDomain(name) ? 0.01 : (name === "noise" ? 2400 : 600);
      }
    },

    createCharts() {
      const specs = {
        temperatureChart: [["brew_boiler_temp", "Brew boiler"], ["steam_boiler_temp", "Steam boiler"], ["ambient_temp", "Ambient"]],
        pressureChart: [["brew_pressure", "Pressure"]],
        flowChart: [["water_flow", "Flow"]],
        currentChart: [["pump_current", "Pump"], ["grinder_current", "Grinder"]],
      };
      const palette = ["#38bdf8", "#a78bfa", "#2dd4bf"];
      for (const [elementId, metrics] of Object.entries(specs)) {
        this.charts[elementId] = new Chart(document.getElementById(elementId), {
          type: "line",
          data: { labels: [], datasets: metrics.map(([key, label], index) => ({
            key, label, data: [], borderColor: palette[index], borderWidth: 2, pointRadius: 2,
            pointBackgroundColor: context => QUALITY_COLORS[context.raw?.quality] || palette[index],
            parsing: { yAxisKey: "value" }, tension: 0.25, spanGaps: true,
          })) },
          options: {
            animation: false, responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { labels: { color: "#cbd5e1" } } },
            scales: {
              x: { ticks: { color: "#64748b", maxTicksLimit: 6 }, grid: { color: "#1e293b" } },
              y: { ticks: { color: "#64748b" }, grid: { color: "#1e293b" } },
            },
          },
        });
      }
    },

    refreshCharts() {
      const records = this.history.slice(-100);
      for (const chart of Object.values(this.charts)) {
        chart.data.labels = records.map(item => this.formatTime(item.timestamp));
        for (const dataset of chart.data.datasets) {
          dataset.data = records.map(item => {
            const metric = item.metrics?.[dataset.key];
            return { value: metric?.value ?? null, quality: metric?.quality || "missing" };
          });
        }
        chart.update("none");
      }
    },

    get activeFaults() { return this.snapshot.active_faults || []; },
    counter(name) { return this.snapshot.counters?.[name] ?? "—"; },
    pmProgress() { return Math.min(100, ((this.snapshot.counters?.shots_since_descale || 0) / 1000) * 100); },
    severity(name) { return Number(this.config.irregularities?.[name]?.severity ?? 0).toFixed(2); },
    isDomain(name) { return DOMAIN_FAULTS.includes(name); },
    rateKey(name) { return this.isDomain(name) ? "mtbf_hours" : "rate_per_hour"; },
    label(name) { return String(name || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); },
    formatTime(value) { return value ? new Date(value).toLocaleString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"; },
    allWorkorders() { return [...this.workorders.open, ...this.workorders.closed].slice(0, 30); },
  }));
});
