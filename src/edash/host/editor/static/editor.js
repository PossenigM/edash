"use strict";

const token = location.hash.slice(1);
const $ = (id) => document.getElementById(id);

const state = {
  data: null,
  saved: "",
  meta: null,
  screen: null,
  selected: null,
  preview: null,
  scale: 1,
  seq: 0,
  notice: null,
  renderMessages: [],
};

const ROTATIONS = [0, 90, 180, 270];
const GRID_DEFAULTS = { cols: 12, rows: 8, gap: 8, margin: 12 };
const PLACEHOLDERS = { duration: "e.g. 45m", timerange: "e.g. 08:00-17:00", weekdays: "e.g. mon-fri" };


async function api(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Edash-Token": token },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "value" || key === "checked" || key === "disabled") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

function select(options, value, onChange) {
  const node = el(
    "select",
    { onchange: (e) => onChange(e.target.value) },
    options.map(([v, label]) => el("option", { value: String(v) }, label)),
  );
  node.value = value === undefined || value === null ? "" : String(value);
  return node;
}

function setKey(obj, key, value) {
  if (value === undefined || value === "") delete obj[key];
  else obj[key] = value;
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const humanize = (name) => name.charAt(0).toUpperCase() + name.slice(1).replaceAll("_", " ");
const screens = () => state.data.screens || [];
const currentScreen = () => screens().find((s) => s.id === state.screen);
const widgets = () => currentScreen()?.widgets || [];
const isBuiltin = () => Boolean(state.screen && state.screen.startsWith("_"));
const ensure = (obj, key, init) => (obj[key] ??= init);
const isTyping = () => ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);


function changed({ rebuild = false } = {}) {
  state.notice = null;
  if (rebuild) rebuildPanels();
  updateDirty();
  scheduleRender();
}

function updateDirty() {
  const dirty = JSON.stringify(state.data) !== state.saved;
  $("dirty").hidden = !dirty;
  $("show-on-panel").disabled = dirty;
  $("show-on-panel").title = dirty ? "Save first" : "Show this screen on the connected display";
}

let renderTimer;
function scheduleRender(delay = 120) {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderPreview, delay);
}

async function renderPreview() {
  const seq = ++state.seq;
  let reply;
  try {
    reply = await api("/api/render", { data: state.data, screen: state.screen, at: $("at").value || null });
  } catch (err) {
    reply = { errors: [String(err)] };
  }
  if (seq !== state.seq) return;
  if (reply.errors) {
    $("stage").classList.add("stale");
    state.renderMessages = reply.errors.map((text) => ({ text, level: "error" }));
    showMessages();
    return;
  }
  $("stage").classList.remove("stale");
  state.preview = reply;
  if (reply.screen !== state.screen) {
    state.screen = reply.screen;
    state.selected = null;
    renderInspector();
  }
  $("frame").src = `data:image/png;base64,${reply.image}`;
  $("active-screen").textContent = `Rules select: ${reply.active_screen}`;
  state.renderMessages = reply.warnings.map((text) => ({ text, level: "warning" }));
  renderScreenList();
  layoutStage();
  drawOverlay();
  showMessages();
}

function showMessages() {
  const list = $("messages");
  list.replaceChildren();
  if (state.notice) {
    for (const text of state.notice.texts) list.append(el("li", { class: state.notice.level }, text));
  }
  for (const m of state.renderMessages) list.append(el("li", { class: m.level }, m.text));
}

function notify(texts, level = "info") {
  state.notice = { texts: [].concat(texts), level };
  showMessages();
}


function layoutStage() {
  if (!state.preview) return;
  const [w, h] = state.preview.size;
  const view = $("preview-view");
  const fit = Math.min((view.clientWidth - 72) / w, (view.clientHeight - 72) / h);
  state.scale = fit >= 1 ? Math.floor(fit * 2) / 2 : Math.max(fit, 0.25);
  const frame = $("frame");
  frame.style.width = `${w * state.scale}px`;
  frame.style.height = `${h * state.scale}px`;
  const overlay = $("overlay");
  overlay.style.width = `${w}px`;
  overlay.style.height = `${h}px`;
  overlay.style.transform = `scale(${state.scale})`;
}

function localBox(widget) {
  if (widget.box) {
    const [x, y, w, h] = widget.box;
    return { x, y, w, h };
  }
  const { cols, rows } = state.preview.grid;
  const [c, r] = widget.pos;
  const [cw, rh] = widget.size;
  const col1 = cols[clamp(c + cw - 1, 0, cols.length - 1)];
  const row1 = rows[clamp(r + rh - 1, 0, rows.length - 1)];
  const x = cols[clamp(c, 0, cols.length - 1)][0];
  const y = rows[clamp(r, 0, rows.length - 1)][0];
  return { x, y, w: col1[1] - x, h: row1[1] - y };
}

const boxStyle = (b) => `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px`;

function drawOverlay() {
  const overlay = $("overlay");
  overlay.replaceChildren();
  if (!state.preview) return;
  overlay.classList.toggle("hide-grid", !$("show-grid").checked);
  overlay.classList.toggle("readonly", isBuiltin());
  const { cols, rows } = state.preview.grid;
  for (const [x0, x1] of cols) {
    for (const [y0, y1] of rows) {
      overlay.append(el("div", { class: "cell", style: boxStyle({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 }) }));
    }
  }
  state.preview.boxes.forEach((box, index) => {
    const type = isBuiltin() ? "away" : widgets()[index]?.type;
    const node = el(
      "div",
      { class: `wbox${index === state.selected ? " selected" : ""}`, style: boxStyle(box) },
      el("span", { class: "label" }, type),
      el("div", { class: "handle" }),
    );
    node.addEventListener("pointerdown", (e) => startDrag(e, index));
    overlay.append(node);
  });
}

function startDrag(event, index) {
  if (isBuiltin() || event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  selectWidget(index);
  const widget = widgets()[index];
  const node = $("overlay").querySelectorAll(".wbox")[index];
  const mode = event.target.classList.contains("handle") ? "resize" : "move";
  const { cols, rows } = state.preview.grid;
  const [width, height] = state.preview.size;
  const pitchX = cols.length > 1 ? cols[1][0] - cols[0][0] : width;
  const pitchY = rows.length > 1 ? rows[1][0] - rows[0][0] : height;
  const start = { x: event.clientX, y: event.clientY, widget: structuredClone(widget) };
  const before = JSON.stringify(widget);
  node.setPointerCapture(event.pointerId);

  const move = (e) => {
    const dx = (e.clientX - start.x) / state.scale;
    const dy = (e.clientY - start.y) / state.scale;
    if (widget.box) {
      const [x, y, w, h] = start.widget.box;
      const snap = (v) => Math.round(v / 4) * 4;
      widget.box =
        mode === "move"
          ? [clamp(snap(x + dx), 0, width - w), clamp(snap(y + dy), 0, height - h), w, h]
          : [x, y, clamp(snap(w + dx), 8, width - x), clamp(snap(h + dy), 8, height - y)];
    } else {
      const [c, r] = start.widget.pos;
      const [cw, rh] = start.widget.size;
      const dc = Math.round(dx / pitchX);
      const dr = Math.round(dy / pitchY);
      if (mode === "move") {
        widget.pos = [clamp(c + dc, 0, cols.length - cw), clamp(r + dr, 0, rows.length - rh)];
      } else {
        widget.size = [clamp(cw + dc, 1, cols.length - c), clamp(rh + dr, 1, rows.length - r)];
      }
    }
    node.style.cssText = boxStyle(localBox(widget));
  };
  const end = () => {
    node.removeEventListener("pointermove", move);
    node.removeEventListener("pointerup", end);
    node.removeEventListener("pointercancel", end);
    if (JSON.stringify(widget) !== before) {
      renderInspector();
      changed();
    }
  };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", end);
  node.addEventListener("pointercancel", end);
}

function selectWidget(index) {
  if (state.selected === index) return;
  state.selected = index;
  $("overlay")
    .querySelectorAll(".wbox")
    .forEach((node, i) => node.classList.toggle("selected", i === index));
  renderInspector();
}


function renderScreenList() {
  const ids = state.preview?.screens || screens().map((s) => s.id);
  const rotation = state.data.rotation || {};
  const list = $("screens");
  list.replaceChildren(
    ...ids.map((id) => {
      const tags = [];
      if (id === (rotation.default || screens()[0]?.id)) tags.push("default");
      if (id.startsWith("_") || id === rotation.away_screen) tags.push("away");
      return el(
        "li",
        { class: id === state.screen ? "active" : "", onclick: () => showScreen(id) },
        id.startsWith("_") ? "Away (built-in)" : id,
        tags.length ? el("span", { class: "tag" }, tags.join(", ")) : null,
      );
    }),
  );
}

function showScreen(id) {
  state.screen = id;
  state.selected = null;
  renderScreenList();
  renderInspector();
  scheduleRender(0);
}

function addScreen() {
  const ids = new Set(screens().map((s) => s.id));
  let n = ids.size + 1;
  while (ids.has(`screen${n}`)) n++;
  ensure(state.data, "screens", []).push({ id: `screen${n}`, widgets: [] });
  state.screen = `screen${n}`;
  state.selected = null;
  changed({ rebuild: true });
}

function renameScreen(oldId, newId, input) {
  newId = newId.trim();
  if (!newId || newId.startsWith("_") || screens().some((s) => s.id === newId)) {
    input.classList.add("invalid");
    notify("Screen ids must be unique, not empty and must not start with '_'.", "error");
    return;
  }
  currentScreen().id = newId;
  const rotation = state.data.rotation;
  if (rotation) {
    if (rotation.default === oldId) rotation.default = newId;
    if (rotation.away_screen === oldId) rotation.away_screen = newId;
    for (const rule of rotation.rules || []) if (rule.screen === oldId) rule.screen = newId;
  }
  state.screen = newId;
  changed({ rebuild: true });
}

function deleteScreen(id) {
  state.data.screens = screens().filter((s) => s.id !== id);
  const rotation = state.data.rotation;
  if (rotation) {
    if (rotation.default === id) rotation.default = screens()[0]?.id;
    if (rotation.away_screen === id) delete rotation.away_screen;
    rotation.rules = (rotation.rules || []).filter((r) => r.screen !== id);
  }
  state.screen = screens()[0]?.id ?? null;
  state.selected = null;
  changed({ rebuild: true });
}


function gridSize() {
  const grid = { ...GRID_DEFAULTS, ...(state.data.display?.grid || {}) };
  return [grid.cols, grid.rows];
}

function freeSpot(size) {
  const [cols, rows] = gridSize();
  const [w, h] = [Math.min(size[0], cols), Math.min(size[1], rows)];
  const taken = widgets().filter((x) => x.pos && x.size);
  for (let r = 0; r + h <= rows; r++) {
    for (let c = 0; c + w <= cols; c++) {
      const free = taken.every(
        (x) => c >= x.pos[0] + x.size[0] || x.pos[0] >= c + w || r >= x.pos[1] + x.size[1] || x.pos[1] >= r + h,
      );
      if (free) return { pos: [c, r], size: [w, h] };
    }
  }
  return { pos: [0, 0], size: [w, h] };
}

function addWidget(type) {
  const options = {};
  for (const f of state.meta.fields[type]) {
    if (f.required) options[f.name] = f.kind === "duration" ? "1h" : f.name === "label" ? "Reminder" : "Text";
  }
  const widget = { type, ...freeSpot([3, 2]) };
  if (Object.keys(options).length) widget.options = options;
  ensure(currentScreen(), "widgets", []).push(widget);
  state.selected = widgets().length - 1;
  changed({ rebuild: true });
}

function duplicateWidget(index) {
  const copy = structuredClone(widgets()[index]);
  if (copy.pos) Object.assign(copy, freeSpot(copy.size));
  widgets().splice(index + 1, 0, copy);
  state.selected = index + 1;
  changed({ rebuild: true });
}

function deleteWidget(index) {
  widgets().splice(index, 1);
  state.preview?.boxes.splice(index, 1);
  state.selected = null;
  drawOverlay();
  changed({ rebuild: true });
}

function setPlacement(widget, mode) {
  if (mode === "box" && !widget.box) {
    const b = localBox(widget);
    delete widget.pos;
    delete widget.size;
    widget.box = [b.x, b.y, b.w, b.h];
  } else if (mode === "grid" && widget.box) {
    const { cols, rows } = state.preview.grid;
    const [x, y, w, h] = widget.box;
    const nearest = (cells, v, side) =>
      cells.reduce((best, cell, i) => (Math.abs(cell[side] - v) < Math.abs(cells[best][side] - v) ? i : best), 0);
    const c0 = nearest(cols, x, 0);
    const r0 = nearest(rows, y, 0);
    const c1 = Math.max(c0, nearest(cols, x + w, 1));
    const r1 = Math.max(r0, nearest(rows, y + h, 1));
    delete widget.box;
    widget.pos = [c0, r0];
    widget.size = [c1 - c0 + 1, r1 - r0 + 1];
  }
  changed({ rebuild: true });
}


function renderInspector() {
  const root = $("inspector");
  root.replaceChildren();
  if (!state.data) return;
  if (isBuiltin()) {
    root.append(
      el("h2", {}, "Built-in away screen"),
      el(
        "p",
        { class: "hint" },
        "Shown while the laptop is locked, asleep or shut down. " +
          "To replace it, create a screen with an away widget and select it under Rotation.",
      ),
    );
    return;
  }
  const screen = currentScreen();
  if (!screen) {
    root.append(el("p", { class: "hint" }, "No screen. Add one on the left."));
    return;
  }
  const widget = widgets()[state.selected];
  if (widget) renderWidgetInspector(root, widget, state.selected);
  else renderScreenInspector(root, screen);
}

function renderScreenInspector(root, screen) {
  const typeSelect = select(
    state.meta.widgets.map((t) => [t, t]),
    state.meta.widgets[0],
    () => {},
  );
  root.append(
    el("h2", {}, "Screen"),
    el(
      "div",
      { class: "form" },
      el("label", {}, "Id"),
      el("input", { value: screen.id, onchange: (e) => renameScreen(screen.id, e.target.value, e.target) }),
    ),
    el(
      "section",
      {},
      el("h3", {}, "Widgets"),
      widgets().length
        ? el(
            "ul",
            { class: "list" },
            widgets().map((w, i) =>
              el(
                "li",
                { onclick: () => selectWidget(i) },
                w.title ? `${w.type}: ${w.title}` : w.type,
                el("span", { class: "tag" }, w.box ? `box ${w.box.join(",")}` : `${w.pos?.join(",")} · ${w.size?.join("×")}`),
              ),
            ),
          )
        : el("p", { class: "hint" }, "No widgets yet."),
      el("div", { class: "row" }, typeSelect, el("button", { type: "button", onclick: () => addWidget(typeSelect.value) }, "Add widget")),
    ),
    el(
      "section",
      {},
      el(
        "button",
        {
          type: "button",
          class: "danger",
          disabled: screens().length < 2,
          title: screens().length < 2 ? "The configuration needs at least one screen" : null,
          onclick: () => deleteScreen(screen.id),
        },
        "Delete screen",
      ),
    ),
  );
}

function renderWidgetInspector(root, widget, index) {
  const update = () => changed();
  const placement = widget.box ? "box" : "grid";
  const numbers = (values, labels, onSet) =>
    el(
      "div",
      { class: "wide" },
      el(
        "div",
        { class: "quad" },
        values.map((value, i) =>
          el("input", {
            type: "number",
            min: i < 2 ? 0 : 1,
            value,
            oninput: (e) => {
              if (e.target.value === "") return;
              onSet(i, Number(e.target.value));
              update();
            },
          }),
        ),
      ),
      el("div", { class: "quad" }, labels.map((l) => el("span", {}, l))),
    );

  root.append(
    el(
      "h2",
      {},
      el("span", { class: "type" }, widget.type),
      el(
        "span",
        { class: "row", style: "margin:0" },
        el("button", { type: "button", class: "small", onclick: () => duplicateWidget(index) }, "Duplicate"),
        el("button", { type: "button", class: "small danger", onclick: () => deleteWidget(index) }, "Delete"),
      ),
    ),
    el(
      "div",
      { class: "form" },
      el("label", {}, "Title"),
      el("input", {
        value: widget.title ?? "",
        oninput: (e) => {
          setKey(widget, "title", e.target.value);
          update();
        },
      }),
      el("label", {}, "Frame"),
      checkbox(widget.frame ?? false, (v) => {
        setKey(widget, "frame", v ? true : undefined);
        update();
      }),
      el("label", {}, "Mark stale data"),
      checkbox(widget.show_stale ?? true, (v) => {
        setKey(widget, "show_stale", v ? undefined : false);
        update();
      }),
    ),
    el(
      "section",
      {},
      el("h3", {}, "Placement"),
      el(
        "div",
        { class: "form" },
        el("label", {}, "Mode"),
        select(
          [
            ["grid", "Grid cells"],
            ["box", "Pixels"],
          ],
          placement,
          (mode) => setPlacement(widget, mode),
        ),
        placement === "grid"
          ? numbers([...widget.pos, ...widget.size], ["col", "row", "cols", "rows"], (i, v) => {
              if (i < 2) widget.pos[i] = v;
              else widget.size[i - 2] = v;
            })
          : numbers(widget.box, ["x", "y", "w", "h"], (i, v) => {
              widget.box[i] = v;
            }),
      ),
    ),
  );

  const fields = state.meta.fields[widget.type];
  if (!fields) {
    root.append(el("p", { class: "hint" }, `Unknown widget type '${widget.type}'.`));
    return;
  }
  if (fields.length) {
    const options = widget.options || {};
    const onChange = () => {
      if (Object.keys(options).length) widget.options = options;
      else delete widget.options;
      update();
    };
    root.append(
      el(
        "section",
        {},
        el("h3", {}, "Options"),
        el(
          "div",
          { class: "form" },
          fields.map((f) => optionControl(options, f, onChange)),
        ),
      ),
    );
  }
}

function checkbox(checked, onChange) {
  return el("input", { type: "checkbox", checked, onchange: (e) => onChange(e.target.checked) });
}

function optionControl(options, f, onChange) {
  const current = options[f.name];
  const set = (value) => {
    const isDefault = !f.required && value !== null && String(value) === String(f.default ?? "");
    if (value === undefined || value === "" || isDefault) delete options[f.name];
    else options[f.name] = value;
    onChange();
  };
  const label = el("label", {}, humanize(f.name) + (f.required ? " *" : ""));
  let input;
  if (f.kind === "bool") {
    input = checkbox(current ?? f.default, set);
  } else if (f.kind === "choice") {
    const choices = f.choices.map((c) => [c, c]);
    if (!f.required) choices.unshift(["", `default${f.default !== null ? ` (${f.default})` : ""}`]);
    input = select(choices, current, (v) => set(v === "" ? undefined : v));
  } else if (f.kind === "int" || f.kind === "float") {
    input = el("input", {
      type: "number",
      min: f.min ?? undefined,
      max: f.max ?? undefined,
      step: f.kind === "float" ? "0.01" : "1",
      value: current ?? "",
      placeholder: f.default ?? "",
      oninput: (e) => set(e.target.value === "" ? undefined : Number(e.target.value)),
    });
  } else {
    input = el("input", {
      value: Array.isArray(current) ? current.join(",") : current ?? "",
      placeholder: f.default ?? PLACEHOLDERS[f.kind] ?? "",
      oninput: (e) => set(e.target.value),
    });
  }
  if (f.nullable && f.default !== null && f.kind !== "bool") {
    input.disabled = current === null;
    const off = el(
      "label",
      { class: "check" },
      checkbox(current === null, (v) => set(v ? null : undefined)),
      "off",
    );
    return [label, el("div", { class: "row", style: "margin:0" }, input, off)];
  }
  return [label, input];
}


function renderDisplayForm() {
  const display = state.data.display || {};
  const grid = display.grid || {};
  const setDisplay = (key, value) => {
    setKey(ensure(state.data, "display", {}), key, value);
    changed();
  };
  const setGrid = (key, value) => {
    const g = ensure(ensure(state.data, "display", {}), "grid", {});
    setKey(g, key, value);
    if (!Object.keys(g).length) delete state.data.display.grid;
    changed();
  };
  const number = (value, placeholder, onChange) =>
    el("input", {
      type: "number",
      min: 0,
      value: value ?? "",
      placeholder,
      oninput: (e) => onChange(e.target.value === "" ? undefined : Number(e.target.value)),
    });
  $("display-form").replaceChildren(
    el("label", {}, "Language"),
    select(
      state.meta.languages.map((l) => [l, l]),
      display.language ?? "en",
      (v) => setDisplay("language", v === "en" ? undefined : v),
    ),
    el("label", {}, "Rotation"),
    select(
      ROTATIONS.map((r) => [r, `${r}°`]),
      display.rotation ?? 0,
      (v) => setDisplay("rotation", Number(v) === 0 ? undefined : Number(v)),
    ),
    ...Object.entries(GRID_DEFAULTS).flatMap(([key, def]) => [
      el("label", {}, `Grid ${key}`),
      number(grid[key], def, (v) => setGrid(key, v)),
    ]),
    el("label", {}, "Full refresh every"),
    el("input", {
      value: display.full_refresh_every ?? "",
      placeholder: "30m",
      oninput: (e) => setDisplay("full_refresh_every", e.target.value),
    }),
    el("label", {}, "Max partial refreshes"),
    number(display.max_partial_refreshes, 60, (v) => setDisplay("max_partial_refreshes", v)),
  );
}

function renderRotationForm() {
  const rotation = state.data.rotation || {};
  const ids = screens().map((s) => [s.id, s.id]);
  const setRotation = (key, value) => {
    const r = ensure(state.data, "rotation", { default: screens()[0]?.id });
    setKey(r, key, value);
    changed();
  };
  $("rotation-form").replaceChildren(
    el("label", {}, "Default screen"),
    select(ids, rotation.default ?? screens()[0]?.id, (v) => {
      setRotation("default", v);
      renderScreenList();
    }),
    el("label", {}, "Away screen"),
    select([["", "built-in"], ...ids], rotation.away_screen, (v) => {
      setRotation("away_screen", v || undefined);
      if (state.screen?.startsWith("_")) state.screen = v || state.screen;
      scheduleRender(0);
    }),
    el("label", {}, "Minimum dwell"),
    el("input", {
      value: rotation.min_dwell ?? "",
      placeholder: "2m",
      oninput: (e) => setRotation("min_dwell", e.target.value),
    }),
  );

  const rules = rotation.rules || [];
  $("rules").replaceChildren(
    ...rules.map((rule, i) =>
      el(
        "div",
        { class: "rule" },
        el("input", {
          value: rule.when,
          placeholder: "meeting_starts_in <= 5m",
          oninput: (e) => {
            rule.when = e.target.value;
            changed();
          },
        }),
        el(
          "button",
          {
            type: "button",
            class: "small danger",
            title: "Remove rule",
            onclick: () => {
              rules.splice(i, 1);
              if (!rules.length) delete state.data.rotation.rules;
              changed({ rebuild: true });
            },
          },
          "×",
        ),
        el(
          "div",
          { class: "row" },
          el("span", { class: "muted" }, "→"),
          select(ids, rule.screen, (v) => {
            rule.screen = v;
            changed();
          }),
        ),
      ),
    ),
  );
}

function addRule() {
  const rotation = ensure(state.data, "rotation", { default: screens()[0]?.id });
  ensure(rotation, "rules", []).push({ when: "meeting_starts_in <= 5m", screen: state.screen && !isBuiltin() ? state.screen : screens()[0]?.id });
  changed({ rebuild: true });
}

function rebuildPanels() {
  renderScreenList();
  renderDisplayForm();
  renderRotationForm();
  renderInspector();
}


async function load() {
  const reply = await api("/api/load");
  state.meta = reply;
  $("path").textContent = reply.path;
  state.data = reply.data ?? { screens: [] };
  state.saved = reply.data ? JSON.stringify(reply.data) : "";
  state.screen = screens()[0]?.id ?? null;
  state.selected = null;
  state.preview = null;
  rebuildPanels();
  updateDirty();
  if (reply.errors) {
    showView("yaml", reply.yaml);
    notify(reply.errors, "error");
  } else {
    scheduleRender(0);
  }
}

async function save() {
  const reply = await api("/api/save", { data: state.data });
  if (reply.errors) {
    notify(reply.errors, "error");
    return;
  }
  state.saved = JSON.stringify(state.data);
  updateDirty();
  notify(`Saved ${reply.path}. A running edash-host sends the new layout to the display.`);
}

async function showOnPanel(screen) {
  const reply = await api("/api/show", { screen });
  if (reply.errors) notify(reply.errors, "error");
  else notify(screen === "auto" ? "Display follows the rotation rules again." : `Display shows '${screen}'.`);
}

async function showView(view, yamlText) {
  for (const button of document.querySelectorAll(".tabs button")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
  $("preview-view").hidden = view !== "preview";
  $("yaml-view").hidden = view !== "yaml";
  if (view === "yaml") {
    $("yaml").value = yamlText ?? (await api("/api/yaml", { data: state.data })).yaml;
  } else {
    layoutStage();
  }
}

async function applyYaml() {
  const reply = await api("/api/parse", { yaml: $("yaml").value });
  if (reply.errors) {
    notify(reply.errors, "error");
    return;
  }
  state.data = reply.data;
  if (!screens().some((s) => s.id === state.screen)) state.screen = screens()[0]?.id ?? null;
  state.selected = null;
  changed({ rebuild: true });
  showView("preview");
}


function nudge(dx, dy) {
  const widget = widgets()[state.selected];
  if (!widget || !state.preview) return;
  const [cols, rows] = [state.preview.grid.cols.length, state.preview.grid.rows.length];
  if (widget.box) {
    const [width, height] = state.preview.size;
    const [x, y, w, h] = widget.box;
    widget.box = [clamp(x + dx * 4, 0, width - w), clamp(y + dy * 4, 0, height - h), w, h];
  } else {
    widget.pos = [clamp(widget.pos[0] + dx, 0, cols - widget.size[0]), clamp(widget.pos[1] + dy, 0, rows - widget.size[1])];
  }
  renderInspector();
  changed();
}

const KEYS = {
  ArrowLeft: () => nudge(-1, 0),
  ArrowRight: () => nudge(1, 0),
  ArrowUp: () => nudge(0, -1),
  ArrowDown: () => nudge(0, 1),
  Delete: () => state.selected !== null && deleteWidget(state.selected),
  Backspace: () => state.selected !== null && deleteWidget(state.selected),
  Escape: () => selectWidget(null),
};

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    save();
    return;
  }
  if (isTyping() || isBuiltin() || !KEYS[e.key]) return;
  e.preventDefault();
  KEYS[e.key]();
});

$("save").addEventListener("click", save);
$("revert").addEventListener("click", () => {
  if (JSON.stringify(state.data) === state.saved || confirm("Discard unsaved changes?")) load();
});
$("add-screen").addEventListener("click", addScreen);
$("add-rule").addEventListener("click", addRule);
$("at").addEventListener("change", () => scheduleRender(0));
$("at-now").addEventListener("click", () => {
  $("at").value = "";
  scheduleRender(0);
});
$("show-grid").addEventListener("change", drawOverlay);
$("show-on-panel").addEventListener("click", () => showOnPanel(state.screen));
$("panel-auto").addEventListener("click", () => showOnPanel("auto"));
$("yaml-apply").addEventListener("click", applyYaml);
$("overlay").addEventListener("pointerdown", (e) => {
  if (!e.target.closest(".wbox")) selectWidget(null);
});
for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => showView(button.dataset.view));
}
window.addEventListener("resize", layoutStage);
window.addEventListener("beforeunload", (e) => {
  if (state.data && JSON.stringify(state.data) !== state.saved) e.preventDefault();
});

load().catch((err) => notify(String(err), "error"));
