const DOMAIN_FAULTS = ["scaling", "grinder_wear", "pump_degradation", "clogged_group", "heater_degradation"];
const GENERIC_FAULTS = ["spike", "drift", "stuck", "dropout", "out_of_range", "noise"];
const FAULTS = [...DOMAIN_FAULTS, ...GENERIC_FAULTS];
const QUALITY_COLORS = { good: "#2dd4bf", suspect: "#f59e0b", bad: "#ef4444", missing: "#64748b" };
const QUALITY_LABELS = { good: "Good", suspect: "Suspect", bad: "Bad", missing: "Missing" };

const METRIC_SPECS = {
  brew_boiler_temp: { unit: "degC", label: "Brew boiler", healthy: [91, 94], group: "temperature" },
  steam_boiler_temp: { unit: "degC", label: "Steam boiler", healthy: [125, 135], group: "temperature" },
  ambient_temp: { unit: "degC", label: "Ambient", healthy: [18, 28], group: "temperature" },
  brew_pressure: { unit: "bar", label: "Brew pressure", healthy: [8.5, 9.5], group: "pressure" },
  water_flow: { unit: "ml_s", label: "Water flow", healthy: [0, 12], group: "flow" },
  pump_current: { unit: "A", label: "Pump", healthy: [0.5, 1.8], group: "current" },
  grinder_current: { unit: "A", label: "Grinder", healthy: [1.5, 3.5], group: "current" },
};

const PM_BANDS = { descale_due_shots: 500, burr_replace_shots: 15000, pm_service_hours: 2000 };

const METRIC_TILES = [
  "brew_boiler_temp", "steam_boiler_temp", "brew_pressure", "water_flow",
  "pump_current", "grinder_current", "ambient_temp",
];

const CHART_SPECS = {
  temperatureChart: {
    title: "Temperatures",
    desc: "Boiler and ambient heat — steady brew temp is critical for extraction quality.",
    unit: "degC",
    metrics: [["brew_boiler_temp", "Brew boiler"], ["steam_boiler_temp", "Steam boiler"], ["ambient_temp", "Ambient"]],
    bandMetric: "brew_boiler_temp",
  },
  pressureChart: {
    title: "Brew pressure",
    desc: "Extraction pressure during a shot — target ~9 bar while brewing.",
    unit: "bar",
    metrics: [["brew_pressure", "Pressure"]],
    bandMetric: "brew_pressure",
  },
  flowChart: {
    title: "Water flow",
    desc: "Flow rate through the group head — spikes during active brewing.",
    unit: "ml_s",
    metrics: [["water_flow", "Flow"]],
    bandMetric: "water_flow",
  },
  currentChart: {
    title: "Motor currents",
    desc: "Pump and grinder draw — unusual spikes can indicate wear or blockage.",
    unit: "A",
    metrics: [["pump_current", "Pump"], ["grinder_current", "Grinder"]],
    bandMetric: "pump_current",
  },
};

const healthyBandPlugin = {
  id: "healthyBand",
  beforeDatasetsDraw(chart, _args, options) {
    const band = options?.band;
    const { ctx, chartArea, scales } = chart;
    if (!band || !chartArea || chartArea.width <= 0 || chartArea.height <= 0) return;
    const yScale = scales.y;
    if (!yScale) return;
    const top = yScale.getPixelForValue(band[1]);
    const bottom = yScale.getPixelForValue(band[0]);
    ctx.save();
    ctx.fillStyle = options.color || "rgba(45, 212, 191, 0.1)";
    ctx.fillRect(chartArea.left, top, chartArea.right - chartArea.left, bottom - top);
    ctx.strokeStyle = options.borderColor || "rgba(45, 212, 191, 0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(chartArea.left, top, chartArea.right - chartArea.left, bottom - top);
    ctx.restore();
  },
};

const EVENT_CATEGORIES = [
  "Machine Issue",
  "Operational Issue",
  "Cleaning",
  "Connectivity Events",
];

const EVENT_SEVERITY_COLORS = {
  Info: "#94a3b8",
  Warning: "#f59e0b",
  Error: "#ef4444",
  Fatal: "#dc2626",
};

function initialEvents() {
  return {
    enabled: true,
    global_rate_multiplier: 1.0,
    categories: Object.fromEntries(
      EVENT_CATEGORIES.map(name => [name, { enabled: true, rate_multiplier: 1.0 }])
    ),
    inject: [],
  };
}

function initialFaults() {
  return Object.fromEntries(FAULTS.map(name => [name, {
    enabled: false,
    severity: 0.5,
    [DOMAIN_FAULTS.includes(name) ? "mtbf_hours" : "rate_per_hour"]: DOMAIN_FAULTS.includes(name) ? 200 : 1,
  }]));
}

function formatUnit(unit) {
  return ({ degC: "°C", bar: "bar", ml_s: "ml/s", A: "A" })[unit] || unit;
}

function healthyHint(metricKey) {
  const spec = METRIC_SPECS[metricKey];
  if (!spec?.healthy) return "";
  const [lo, hi] = spec.healthy;
  return `${lo}–${hi} ${formatUnit(spec.unit)}`;
}

document.addEventListener("alpine:init", () => {
  Alpine.data("dashboard", () => {
    // Chart.js instances must stay OUT of Alpine's reactive proxy — wrapping them
    // corrupts Chart's internal state so the axes render but data never plots.
    const chartRegistry = {};
    return {
    devices: [],
    selectedId: "",
    snapshot: {},
    history: [],
    events: [],
    eventFilter: { severity: "", category: "" },
    workorders: { open: [], closed: [] },
    config: {
      sample_interval_ms: 1000,
      publish_interval_s: 30,
      irregularities: initialFaults(),
      events: initialEvents(),
    },
    faultNames: FAULTS,
    eventCategories: EVENT_CATEGORIES,
    metricTiles: METRIC_TILES,
    chartSpecs: CHART_SPECS,
    qualityLegend: Object.entries(QUALITY_LABELS).map(([key, label]) => ({ key, label, color: QUALITY_COLORS[key] })),
    socket: null,
    reconnectTimer: null,
    lastAck: null,
    error: "",
    notice: "",
    saving: false,

    async init() {
      await new Promise(resolve => requestAnimationFrame(resolve));
      try {
        this.createCharts();
      } catch (error) {
        this.error = `Chart setup failed: ${error.message}`;
        console.error(error);
      }
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
        let events = [];
        try {
          events = await this.request(`/api/events/${id}`);
        } catch (_error) {
          events = [];
        }
        this.snapshot = snapshot;
        this.history = history;
        this.workorders = workorders;
        this.events = events;
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
          this.events = data.events || [];
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
      } else if (event.type === "event") {
        this.events.unshift(event.data);
        this.events = this.events.slice(0, 500);
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
      const events = initialEvents();
      if (applied.events) {
        if (typeof applied.events.enabled === "boolean") events.enabled = applied.events.enabled;
        if (applied.events.global_rate_multiplier != null) {
          events.global_rate_multiplier = applied.events.global_rate_multiplier;
        }
        if (Array.isArray(applied.events.inject)) events.inject = applied.events.inject;
        if (applied.events.categories) {
          for (const name of EVENT_CATEGORIES) {
            if (!events.categories[name]) {
              events.categories[name] = { enabled: true, rate_multiplier: 1.0 };
            }
            Object.assign(events.categories[name], applied.events.categories[name] || {});
          }
        }
      }
      this.config = {
        sample_interval_ms: applied.sample_interval_ms ?? 1000,
        publish_interval_s: applied.publish_interval_s ?? 30,
        irregularities: merged,
        events,
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
      this.config.events = initialEvents();
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
      this.config.events = {
        enabled: true,
        global_rate_multiplier: 3.0,
        categories: Object.fromEntries(
          EVENT_CATEGORIES.map(name => [name, { enabled: true, rate_multiplier: 2.0 }])
        ),
        inject: [],
      };
    },

    createCharts() {
      if (typeof Chart === "undefined") throw new Error("Chart.js did not load");
      if (!Chart.registry.plugins.get("healthyBand")) Chart.register(healthyBandPlugin);

      const palette = ["#38bdf8", "#a78bfa", "#2dd4bf", "#f472b6"];
      for (const [elementId, spec] of Object.entries(CHART_SPECS)) {
        const bandMetric = spec.bandMetric;
        const healthy = METRIC_SPECS[bandMetric]?.healthy;
        const unitLabel = formatUnit(spec.unit);
        const canvas = document.getElementById(elementId);
        if (!canvas) throw new Error(`Missing chart canvas: ${elementId}`);

        chartRegistry[elementId] = new Chart(canvas, {
          type: "line",
          data: {
            labels: [],
            datasets: spec.metrics.map(([metricKey, label], index) => {
              const colorIndex = index;
              return {
              metricKey,
              label,
              data: [],
              _qualities: [],
              _windows: [],
              borderColor: palette[colorIndex % palette.length],
              backgroundColor: palette[colorIndex % palette.length] + "22",
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 5,
              pointBackgroundColor: context => {
                const quality = context.dataset._qualities?.[context.dataIndex];
                return QUALITY_COLORS[quality] || palette[colorIndex % palette.length];
              },
              pointBorderColor: "#0f172a",
              pointBorderWidth: 1,
              tension: 0.25,
              spanGaps: true,
            };
            }),
          },
          options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: {
                position: "top",
                align: "end",
                labels: { color: "#cbd5e1", boxWidth: 10, boxHeight: 10, padding: 14, font: { size: 11 } },
              },
              healthyBand: {
                band: healthy,
                color: "rgba(45, 212, 191, 0.08)",
                borderColor: "rgba(45, 212, 191, 0.3)",
              },
              tooltip: {
                backgroundColor: "#0f172a",
                borderColor: "#334155",
                borderWidth: 1,
                titleColor: "#e2e8f0",
                bodyColor: "#cbd5e1",
                footerColor: "#94a3b8",
                padding: 12,
                callbacks: {
                  title: items => items[0]?.label || "",
                  label: context => {
                    const value = context.parsed.y;
                    if (value == null) return `${context.dataset.label}: no data`;
                    const unit = formatUnit(METRIC_SPECS[context.dataset.metricKey]?.unit || spec.unit);
                    const quality = context.dataset._qualities?.[context.dataIndex] || "missing";
                    return `${context.dataset.label}: ${value} ${unit} (${QUALITY_LABELS[quality] || quality})`;
                  },
                  afterBody: items => {
                    const lines = [];
                    for (const item of items) {
                      const window = item.dataset._windows?.[item.dataIndex];
                      if (!window) continue;
                      const unit = formatUnit(METRIC_SPECS[item.dataset.metricKey]?.unit || spec.unit);
                      lines.push(`${item.dataset.label} window: min ${window.min}, max ${window.max}, avg ${window.mean} ${unit}`);
                    }
                    return lines;
                  },
                  footer: () => healthy ? `Healthy band: ${healthy[0]}-${healthy[1]} ${unitLabel}` : "",
                },
              },
            },
            scales: {
              x: {
                ticks: { color: "#64748b", maxTicksLimit: 6, font: { size: 10 } },
                grid: { color: "#1e293b" },
                title: { display: true, text: "Time", color: "#64748b", font: { size: 10, weight: 600 } },
              },
              y: {
                ticks: { color: "#64748b", font: { size: 10 } },
                grid: { color: "#1e293b" },
                title: { display: true, text: unitLabel, color: "#64748b", font: { size: 10, weight: 600 } },
              },
            },
          },
        });
      }
    },

    chartRecords() {
      const records = this.history.slice(-100);
      if (records.length) return records;
      if (this.snapshot?.metrics && Object.keys(this.snapshot.metrics).length) {
        return [this.snapshot];
      }
      return [];
    },

    refreshCharts() {
      if (!Object.keys(chartRegistry).length) return;
      const records = this.chartRecords();
      for (const chart of Object.values(chartRegistry)) {
        chart.data.labels = records.map(item => this.formatTime(item.timestamp));
        for (const dataset of chart.data.datasets) {
          dataset.data = records.map(item => item.metrics?.[dataset.metricKey]?.value ?? null);
          dataset._qualities = records.map(item => item.metrics?.[dataset.metricKey]?.quality || "missing");
          dataset._windows = records.map(item => {
            const metric = item.metrics?.[dataset.metricKey];
            return metric?.min != null ? { min: metric.min, max: metric.max, mean: metric.mean } : null;
          });
        }
        chart.update("none");
        if (typeof chart.resize === "function") chart.resize();
      }
    },

    get activeFaults() { return this.snapshot.active_faults || []; },
    get latestRecord() { return this.history.length ? this.history[this.history.length - 1] : null; },

    counter(name) { return this.snapshot.counters?.[name] ?? "—"; },

    metric(key) {
      const reading = this.latestRecord?.metrics?.[key] || this.snapshot.metrics?.[key];
      return reading || null;
    },

    metricValue(key) {
      const reading = this.metric(key);
      if (!reading || reading.value == null) return "—";
      const unit = formatUnit(reading.unit || METRIC_SPECS[key]?.unit);
      return `${reading.value} ${unit}`;
    },

    metricQuality(key) {
      return this.metric(key)?.quality || "missing";
    },

    metricLabel(key) { return METRIC_SPECS[key]?.label || this.label(key); },

    metricHealthy(key) { return healthyHint(key); },

    pmProgress() {
      const shots = this.snapshot.counters?.shots_since_descale || 0;
      return Math.min(100, (shots / PM_BANDS.descale_due_shots) * 100);
    },

    pmLabel() {
      const shots = this.snapshot.counters?.shots_since_descale ?? "—";
      return `${shots} / ${PM_BANDS.descale_due_shots} shots`;
    },

    pmDue() {
      return (this.snapshot.counters?.shots_since_descale || 0) >= PM_BANDS.descale_due_shots;
    },

    pmAdvisories() {
      const advisories = [];
      const counters = this.snapshot.counters || {};
      if ((counters.shots_since_descale || 0) >= PM_BANDS.descale_due_shots) advisories.push("Descale due");
      if ((counters.total_shots || 0) >= PM_BANDS.burr_replace_shots) advisories.push("Burr replace due");
      if ((counters.operating_hours || 0) >= PM_BANDS.pm_service_hours) advisories.push("PM service due");
      return advisories;
    },

    windowInfo() {
      const window = this.latestRecord?.window;
      if (!window?.sample_count) return "";
      return `Window: ${window.sample_count} samples`;
    },

    stateClass() {
      const state = this.snapshot.state || "unknown";
      return `state-${state}`;
    },

    severityBadge(value) {
      if (typeof value === "string") {
        if (value === "critical" || value === "Fatal") return "critical";
        if (value === "high" || value === "Error") return "warning";
        if (value === "medium" || value === "Warning") return "warning";
        return "info";
      }
      const num = Number(value);
      if (num >= 0.75) return "critical";
      if (num >= 0.4) return "warning";
      return "info";
    },

    severity(name) { return Number(this.config.irregularities?.[name]?.severity ?? 0).toFixed(2); },
    isDomain(name) { return DOMAIN_FAULTS.includes(name); },
    rateKey(name) { return this.isDomain(name) ? "mtbf_hours" : "rate_per_hour"; },
    label(name) { return String(name || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); },
    formatTime(value) {
      return value ? new Date(value).toLocaleString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
    },
    formatDateTime(value) {
      return value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
    },
    allWorkorders() { return [...this.workorders.open, ...this.workorders.closed].slice(0, 30); },
    openWorkorderCount() { return this.workorders.open?.length || 0; },
    filteredEvents() {
      return this.events.filter(record => {
        const event = record.event || {};
        if (this.eventFilter.severity && event.severity !== this.eventFilter.severity) return false;
        if (this.eventFilter.category && event.category !== this.eventFilter.category) return false;
        return true;
      }).slice(0, 100);
    },
    eventSeverityColor(severity) {
      return EVENT_SEVERITY_COLORS[severity] || "#64748b";
    },
    eventTransitionLabel(transition) {
      return ({ raised: "Raised", cleared: "Cleared", momentary: "Momentary" })[transition] || transition;
    },
    woSeverityLabel(value) {
      if (typeof value === "string") return value;
      return Number(value).toFixed(2);
    },
    chartHealthyHint(chartId) {
      const spec = CHART_SPECS[chartId];
      if (!spec) return "";
      if (spec.metrics.length === 1) return `Healthy: ${healthyHint(spec.metrics[0][0])}`;
      return spec.metrics.map(([key]) => `${METRIC_SPECS[key]?.label}: ${healthyHint(key)}`).join(" · ");
    },
    };
  });
});
