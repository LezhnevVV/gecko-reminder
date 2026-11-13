/* Gecko Reminder 0.1.2 — no build step or external dependencies. */
const INSECTS = {cricket: "Сверчок", locust: "Саранча", dubia: "Таракан дубия", mealworm: "Мучной червь", superworm: "Зофобас", other: "Другое"};
const SUPPLEMENTS = {none: "Без добавки", calcium: "Кальций", calcium_d3: "Кальций + D3", vitamins: "Витамины"};
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const dateKey = (year, month, day) => `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

class GeckoFeedingCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.shadowRoot.addEventListener("click", (event) => this._click(event));
    this.shadowRoot.addEventListener("submit", (event) => this._submit(event));
    this._busy = false;
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Укажите entity датчика Gecko Reminder");
    this._config = {...config};
    this._renderShell();
    if (this._hass) this._refresh();
  }

  set hass(hass) {
    const previous = this._hass?.states[this._config?.entity];
    this._hass = hass;
    if (this._config && (previous !== hass.states[this._config.entity] || !this._month)) this._refresh();
  }

  getCardSize() { return 10; }
  getGridOptions() { return {columns: 12, min_columns: 6, rows: 10}; }
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((id) => id.startsWith("sensor.") && Array.isArray(hass.states[id].attributes.entries));
    return {entity: entity || "sensor.gecko_reminder_feedings", title: "Дневник эублефара"};
  }

  _today() {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: this._hass?.config?.time_zone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((p) => [p.type, p.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; --gecko-accent:var(--primary-color,#47745a); }
        * { box-sizing:border-box; }
        ha-card { display:block; overflow:hidden; color:var(--primary-text-color,#25352d); background:var(--card-background-color,#fff); border-radius:20px; }
        header { padding:24px 24px 14px; display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
        h2 { margin:0 0 5px; font-size:22px; font-weight:650; } p { margin:0; }
        .muted, #summary { color:var(--secondary-text-color,#67766d); font-size:13px; }
        button, input, select, textarea { font:inherit; }
        button { cursor:pointer; min-height:42px; border:1px solid var(--divider-color,#dae3dc); border-radius:10px; padding:8px 13px; background:var(--card-background-color,#fff); color:inherit; }
        button:hover { border-color:var(--gecko-accent); }
        button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline:3px solid var(--gecko-accent); outline-offset:2px; }
        button:disabled { cursor:wait; opacity:.55; }
        .primary { background:var(--gecko-accent); color:var(--text-primary-color,#fff); border-color:transparent; }
        nav { display:flex; align-items:center; gap:8px; padding:10px 24px 20px; flex-wrap:wrap; }
        #month { text-transform:capitalize; font-size:19px; font-weight:600; margin-right:auto; }
        .scroll { overflow-x:auto; padding:0 18px 18px; }
        .week, #calendar { display:grid; grid-template-columns:repeat(7,minmax(112px,1fr)); min-width:820px; gap:7px; }
        .week span { padding:8px; color:var(--secondary-text-color,#67766d); font-size:12px; }
        .week span:nth-last-child(-n+2) { color:var(--gecko-accent); }
        .day { position:relative; display:flex; flex-direction:column; min-height:145px; border:1px solid var(--divider-color,#e4e9e4); border-radius:12px; padding:8px; background:var(--secondary-background-color,#f8faf7); }
        .day.fed { background:#e4f3e7; background:color-mix(in srgb, var(--card-background-color,#fff) 80%, #78bd89); }
        .day.unfed { background:#fceef1; background:color-mix(in srgb, var(--card-background-color,#fff) 85%, #e8a1b3); }
        .day.today { border:2px solid var(--gecko-accent); padding:7px; }
        .day.empty { opacity:.25; }
        .date-number { position:absolute; top:11px; left:13px; font-size:14px; font-weight:600; pointer-events:none; }
        .date { display:grid; place-items:center; flex:1; width:100%; border:0; min-height:110px; padding:20px 5px; background:transparent; }
        .date span { color:var(--gecko-accent); font-size:48px; line-height:1; font-weight:400; }
        .feeding { text-align:left; display:block; width:100%; margin-top:6px; padding:8px; background:var(--card-background-color,#fff); border-radius:8px; overflow-wrap:anywhere; }
        .feeding strong { display:block; font-size:12px; line-height:1.5; }
        .supplement { display:inline-block; margin-top:5px; font-size:10px; padding:3px 5px; border-radius:5px; background:var(--secondary-background-color,#edf1ed); }
        .supplement.calcium, .supplement.calcium_d3 { color:var(--primary-text-color,#334c66); border-left:3px solid #7babc2; }
        .supplement.vitamins { color:var(--primary-text-color,#6b5426); border-left:3px solid #cba357; }
        footer { padding:0 24px 20px; display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:var(--secondary-text-color,#67766d); }
        #status { margin:0 24px 12px; font-size:14px; color:var(--error-color,#b3261e); } #status:empty { display:none; }
        dialog { width:min(460px,calc(100vw - 24px)); max-height:90vh; overflow:auto; padding:24px; border:1px solid var(--divider-color,#dae3dc); border-radius:18px; background:var(--card-background-color,#fff); color:var(--primary-text-color,#25352d); }
        dialog::backdrop { background:#101d1966; } h3 { margin:0 0 20px; font-size:21px; }
        form { display:grid; gap:14px; } label { display:grid; gap:6px; font-size:13px; }
        input, select, textarea { width:100%; min-width:0; padding:11px; border:1px solid var(--divider-color,#cbd6cc); border-radius:8px; color:inherit; background:var(--card-background-color,#fff); }
        textarea { resize:vertical; } .two { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; } .actions .primary { margin-left:auto; }
        .danger { color:var(--error-color,#b3261e); } #form-error { color:var(--error-color,#b3261e); font-size:13px; }
        @media(max-width:500px) { header { padding:18px 16px 12px; } nav { padding:8px 16px 16px; } .scroll { padding:0 10px 16px; } h2 { font-size:20px; } }
      </style>
      <ha-card>
        <header><div><h2>${escapeHTML(this._config.title || "Дневник эублефара")}</h2><p id="summary"></p></div><button class="primary" data-action="add">+ Кормление</button></header>
        <nav aria-label="Выбор месяца"><span id="month"></span><button data-action="prev" aria-label="Предыдущий месяц">←</button><button data-action="today">Сегодня</button><button data-action="next" aria-label="Следующий месяц">→</button></nav>
        <p id="status" role="status"></p>
        <div class="scroll" tabindex="0" aria-label="Календарь кормлений, прокручивается горизонтально">
          <div class="week">${["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"].map((d) => `<span>${d}</span>`).join("")}</div>
          <div id="calendar"></div>
        </div>
        <footer><span>Нажмите на дату, чтобы добавить кормление</span><span>На телефоне листайте календарь вбок →</span></footer>
      </ha-card>
      <dialog aria-labelledby="form-title"><form>
        <h3 id="form-title">Кормление</h3>
        <label>Дата кормления<input name="date" type="date" required></label>
        <div class="two"><label>Насекомое<select name="insect">${Object.entries(INSECTS).map(([k,v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label>Количество, шт.<input name="count" type="number" min="1" max="1000" step="1" value="1" required></label></div>
        <label>Добавка<select name="supplement">${Object.entries(SUPPLEMENTS).map(([k,v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label>Заметка<textarea name="notes" rows="2" maxlength="500" placeholder="Необязательно"></textarea></label>
        <p id="form-error" role="alert"></p>
        <div class="actions"><button type="button" class="danger" data-action="delete">Удалить</button><button type="button" data-action="cancel">Отмена</button><button type="submit" class="primary">Сохранить</button></div>
      </form></dialog>`;
    this.shadowRoot.querySelector("dialog").addEventListener("cancel", (event) => {
      if (this._busy) event.preventDefault();
    });
  }

  _refresh() {
    if (!this._month) {
      const [year, month] = this._today().split("-").map(Number);
      this._month = new Date(year, month - 1, 1);
    }
    const state = this._hass.states[this._config.entity];
    this._available = !!state && !["unavailable", "unknown"].includes(state.state) && Array.isArray(state.attributes.entries);
    this._entries = this._available ? state.attributes.entries : [];
    this.shadowRoot.querySelector("#status").textContent = this._available ? "" : `Датчик ${this._config.entity} недоступен. Проверьте интеграцию и entity в настройках карточки.`;
    this.shadowRoot.querySelector('[data-action="add"]').disabled = !this._available;
    const year = this._month.getFullYear(), month = this._month.getMonth();
    this.shadowRoot.querySelector("#month").textContent = this._month.toLocaleDateString("ru-RU", {month: "long", year: "numeric"});
    const prefix = dateKey(year, month, 1).slice(0, 7);
    const monthEntries = this._entries.filter((e) => e.date.startsWith(prefix));
    this.shadowRoot.querySelector("#summary").textContent = `${monthEntries.length} кормлений · ${monthEntries.reduce((n, e) => n + e.count, 0)} насекомых за месяц`;
    const byDay = new Map();
    monthEntries.forEach((e) => { if (!byDay.has(e.date)) byDay.set(e.date, []); byDay.get(e.date).push(e); });
    const offset = (this._month.getDay() + 6) % 7;
    const days = new Date(year, month + 1, 0).getDate();
    let html = '<div class="day empty" aria-hidden="true"></div>'.repeat(offset);
    for (let day = 1; day <= days; day++) {
      const key = dateKey(year, month, day);
      const feedingStatus = this._available ? (byDay.has(key) ? "fed" : "unfed") : "";
      html += `<div class="day ${key === this._today() ? "today" : ""} ${feedingStatus}"><span class="date-number">${day}</span><button class="date" data-date="${key}" ${!this._available ? "disabled" : ""} aria-label="Добавить кормление ${key}"><span aria-hidden="true">+</span></button>`;
      html += (byDay.get(key) || []).map((e) => `<button class="feeding" data-id="${escapeHTML(e.id)}" title="${escapeHTML(e.notes || "Изменить кормление")}" aria-label="${escapeHTML(`${key}: ${INSECTS[e.insect] || e.insect}, ${e.count} шт., ${SUPPLEMENTS[e.supplement] || e.supplement}. Изменить`)}"><strong>${escapeHTML(INSECTS[e.insect] || e.insect)} · ${escapeHTML(e.count)} шт.</strong><span class="supplement ${escapeHTML(e.supplement)}">${escapeHTML(SUPPLEMENTS[e.supplement] || e.supplement)}</span>${e.notes ? '<span aria-label="Есть заметка"> · ✎</span>' : ""}</button>`).join("");
      html += "</div>";
    }
    html += '<div class="day empty" aria-hidden="true"></div>'.repeat((7 - (offset + days) % 7) % 7);
    this.shadowRoot.querySelector("#calendar").innerHTML = html;
  }

  _click(event) {
    const button = event.target.closest("button");
    if (!button || this._busy) return;
    const action = button.dataset.action;
    if (action === "prev" || action === "next") {
      this._month.setMonth(this._month.getMonth() + (action === "next" ? 1 : -1));
      this._refresh();
    } else if (action === "today") {
      this._month = null;
      this._refresh();
    } else if (action === "add" || button.dataset.date) {
      if (this._available) this._open({date: button.dataset.date || this._today(), count: 1, insect: "cricket", supplement: "none", notes: ""});
    } else if (button.dataset.id) {
      const entry = this._entries.find((e) => e.id === button.dataset.id);
      if (entry) this._open(entry);
    } else if (action === "cancel") {
      this.shadowRoot.querySelector("dialog").close();
    } else if (action === "delete" && this._editingId) {
      if (window.confirm("Удалить это кормление из дневника?")) this._save("delete_feeding", {id: this._editingId});
    }
  }

  _open(entry) {
    const form = this.shadowRoot.querySelector("form");
    this._editingId = entry.id;
    for (const name of ["date", "insect", "count", "supplement", "notes"]) form.elements.namedItem(name).value = entry[name] ?? "";
    this.shadowRoot.querySelector("#form-title").textContent = entry.id ? "Изменить кормление" : "Новое кормление";
    this.shadowRoot.querySelector('[data-action="delete"]').hidden = !entry.id;
    this.shadowRoot.querySelector("#form-error").textContent = "";
    this.shadowRoot.querySelector("dialog").showModal();
  }

  _submit(event) {
    event.preventDefault();
    if (this._busy || !event.target.reportValidity()) return;
    const data = Object.fromEntries(new FormData(event.target));
    data.count = Number(data.count);
    if (this._editingId) data.id = this._editingId;
    this._save("save_feeding", data);
  }

  async _save(service, data) {
    this._busy = true;
    const fields = this.shadowRoot.querySelectorAll("dialog button, dialog input, dialog select, dialog textarea");
    fields.forEach((el) => { el.disabled = true; });
    try {
      await this._hass.callService("gecko_reminder", service, data);
      this.shadowRoot.querySelector("dialog").close();
    } catch (error) {
      this.shadowRoot.querySelector("#form-error").textContent = `Не удалось сохранить: ${error.message || error}`;
    } finally {
      this._busy = false;
      fields.forEach((el) => { el.disabled = false; });
    }
  }
}

if (!customElements.get("gecko-feeding-card")) customElements.define("gecko-feeding-card", GeckoFeedingCard);
window.customCards = window.customCards || [];
window.customCards.push({type: "gecko-feeding-card", name: "Gecko Reminder", description: "Календарь кормлений питомца", preview: true});
