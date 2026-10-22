"use strict";
const $ = (id) => document.getElementById(id);
const dialog = $("password-dialog");
const settingsDialog = $("settings-dialog");
let state = null, lastChallenge = null, submitting = false, polling = false;
let failedPolls = 0, toastTimer, audio = null, soundEnabled = false;
let adminAuthed = false, adminBusy = false;
let historyOffset = 0, historyTotal = 0, historyBusy = false, historySeq = 0;
let loadedRevision = null, historyFilter = {kind: "all", date: ""};
let lastOpenNotice = 0;

function prepareAudio(force = false) {
  if (!soundEnabled && !force) return;
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    if (!audio) audio = new Audio();
    if (audio.state === "suspended") audio.resume().catch(() => {});
  } catch {}
}
document.addEventListener("pointerdown", () => prepareAudio());
document.addEventListener("keydown", () => prepareAudio());

function playSound(kind = "success", force = false) {
  if ((!soundEnabled && !force) || !audio || audio.state !== "running") return;
  const notes = kind === "error" ? [220, 165] : kind === "closed" ? [440, 330] : [660, 880];
  try {
    notes.forEach((frequency, index) => {
      const osc = audio.createOscillator(), gain = audio.createGain();
      const start = audio.currentTime + index * 0.16;
      osc.type = "sine"; osc.frequency.value = frequency;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.05, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.14);
      osc.connect(gain); gain.connect(audio.destination);
      osc.start(start); osc.stop(start + 0.15);
      osc.onended = () => { osc.disconnect(); gain.disconnect(); };
    });
  } catch {}
}

function toast(message, type = "info") {
  $("toast-message").textContent = message;
  $("toast-icon").textContent = type === "error" ? "!" : type === "success" ? "✓" : "i";
  $("toast").dataset.type = type;
  $("toast").hidden = false;
  if ($("toast").showPopover && !$("toast").matches(":popover-open")) $("toast").showPopover();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    if ($("toast").hidePopover && $("toast").matches(":popover-open")) $("toast").hidePopover();
    $("toast").hidden = true;
  }, 5000);
}
function noticeOpen() {
  if (Date.now() - lastOpenNotice < 2500) return;
  lastOpenNotice = Date.now();
  toast("Acceso autorizado. La puerta se cerrará en 5 segundos.", "success");
  playSound("success");
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.body === undefined ? "GET" : "POST",
    cache: "no-store", credentials: "same-origin",
    headers: options.body === undefined ? {} : {"Content-Type": "application/json"},
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(options.timeout || 5000)
  });
  let result;
  try { result = await response.json(); } catch { throw new Error("Respuesta inválida del servidor."); }
  if (!response.ok) {
    const error = new Error(typeof result.detail === "string" ? result.detail : "Revisa los datos e inténtalo otra vez.");
    error.status = response.status; throw error;
  }
  return result;
}
function messageFor(error) {
  return error.name === "TimeoutError" ? "La aplicación no respondió a tiempo. Revisa la terminal." : error.message;
}

function showPanel() {
  if (!state?.challenge || !state.connected || settingsDialog.open) return false;
  $("password").value = ""; $("password").type = "password";
  $("toggle-password").textContent = "Ver";
  $("toggle-password").setAttribute("aria-label", "Mostrar contraseña");
  $("form-message").textContent = "";
  if (!dialog.open) dialog.showModal();
  $("password").focus();
  return true;
}
function applyPreferences(settings) {
  if (!settings) return;
  soundEnabled = settings.sound_enabled;
  $("house-name").textContent = settings.name;
  $("welcome-title").textContent = settings.name === "Mi casa" ? "Bienvenido a casa." : "Bienvenido a " + settings.name + ".";
  document.title = "Kamehouse Sec · Acceso conectado";
  $("sound-status").textContent = soundEnabled ? "♪ Sonido activado" : "♪ Sonido desactivado";
}
function formatDate(value, options) {
  if (!value || Number.isNaN(Date.parse(value))) return "—";
  return new Intl.DateTimeFormat("es-CL", {timeZone: "America/Santiago", ...options}).format(new Date(value));
}
function render(next) {
  const previous = state;
  state = next;
  const connected = next.connected, demo = next.mode === "demo";
  applyPreferences(next.settings);
  document.body.classList.toggle("door-open", connected && next.opened);
  document.body.classList.toggle("person-present", connected && next.present);
  $("connection-dot").classList.toggle("on", connected);
  $("connection-text").textContent = next.server_unreachable ? "Aplicación sin respuesta" : connected ? (demo ? "Modo demostración" : "Arduino conectado · " + next.port) : next.usb_open ? "USB abierto · esperando datos" : "Arduino desconectado";
  $("diag-server").textContent = next.server_unreachable ? "Sin respuesta" : "En línea";
  $("diag-usb").textContent = next.server_unreachable ? "Sin confirmar" : demo ? "Simulado" : next.usb_open ? next.port + " · abierto" : "Sin conexión";
  $("diag-data").textContent = next.server_unreachable ? "Sin confirmar" : demo ? "Datos simulados" : connected ? "Al día" : next.usb_open ? "Esperando datos válidos" : "Sin datos";
  $("diag-server").dataset.status = next.server_unreachable ? "warning" : "ok";
  $("diag-usb").dataset.status = next.server_unreachable || (!demo && !next.usb_open) ? "warning" : "ok";
  $("diag-data").dataset.status = connected ? "ok" : "warning";
  $("demo-banner").hidden = !demo;
  $("demo-toggle").textContent = next.present ? "Alejar persona del sensor" : "Acercar persona al sensor";
  $("distance").textContent = connected && next.distance_cm != null ? Number(next.distance_cm).toFixed(1) + " cm" : "— cm";
  $("sensor-status").textContent = !connected ? "Sin conexión" : next.present ? "Persona detectada" : "Sin presencia";
  $("door-status").textContent = !connected ? "Sin confirmación" : next.opened ? "Abierta · 90°" : "Cerrada · 0°";
  $("door-tag").textContent = !connected ? "Sin conexión" : next.opened ? "Puerta abierta" : "Puerta cerrada";
  $("door-tag").classList.toggle("open", connected && next.opened);
  $("show-panel").hidden = !next.challenge;
  $("countdown").hidden = !connected || !next.opened;
  $("seconds").textContent = Math.max(0, Math.ceil((next.remaining_ms || 0) / 1000));
  $("countdown-progress").value = next.remaining_ms || 0;

  let title, description, icon, caption;
  if (!connected) {
    title = next.server_unreachable ? "Revisa la aplicación" : next.usb_open ? "Esperando al Arduino" : "Conecta tu casa";
    description = next.message; icon = "↔"; caption = "Esperando conexión con la casa";
  } else if (next.opened) {
    title = "Adelante, estás en casa."; description = "Acceso autorizado. La puerta se cerrará automáticamente.";
    icon = "✓"; caption = "Acceso autorizado · puerta abierta";
  } else if (next.needs_clear) {
    title = "Puerta cerrada."; description = "Aléjate del sensor y vuelve a acercarte para iniciar otro acceso.";
    icon = "⌂"; caption = "Ciclo completado · esperando que te alejes";
  } else if (next.present) {
    title = "Hay alguien en la entrada."; description = "Ingresa la contraseña para autorizar la apertura de la puerta.";
    icon = "◎"; caption = "Persona detectada · esperando contraseña";
  } else {
    title = "Todo listo para tu llegada."; description = "Acércate a 10 cm o menos del sensor para activar el panel de acceso.";
    icon = "⌂"; caption = "Puerta cerrada · esperando presencia";
  }
  $("status-title").textContent = title; $("status-description").textContent = description;
  $("status-icon").textContent = icon; $("scene-caption").textContent = caption;
  $("unlock-button").disabled = submitting || next.blocked_seconds > 0;
  $("admin-login-form").querySelector('button[type="submit"]').disabled = adminBusy || next.blocked_seconds > 0;
  if (next.blocked_seconds > 0) {
    $("form-message").textContent = "Espera " + next.blocked_seconds + " segundos para volver a intentar.";
    if (!adminAuthed) $("admin-message").textContent = $("form-message").textContent;
  } else {
    for (const id of ["form-message", "admin-message"]) {
      if ($(id).textContent.startsWith("Espera ")) $(id).textContent = "";
    }
  }
  if (!next.challenge) {
    if (dialog.open) dialog.close();
    $("password").value = "";
    if (!submitting) lastChallenge = null;
  } else if (next.challenge !== lastChallenge && !submitting) {
    if (showPanel()) lastChallenge = next.challenge;
  }
  if (previous?.connected && connected) {
    if (!previous.opened && next.opened) noticeOpen();
    if (previous.opened && !next.opened) {
      toast("Puerta cerrada automáticamente.", "info"); playSound("closed");
    }
  }
  const stats = next.statistics;
  if (stats) {
    $("stat-openings").textContent = stats.openings_today;
    $("stat-denied").textContent = stats.denied_today;
    $("stat-last-time").textContent = stats.last_entry ? formatDate(stats.last_entry, {hour: "2-digit", minute: "2-digit"}) : "Sin entradas";
    $("stat-last-date").textContent = stats.last_entry ? formatDate(stats.last_entry, {day: "2-digit", month: "long", year: "numeric"}) : "Aún no se registran aperturas";
    const revision = next.mode + ":" + stats.revision;
    if (!next.server_unreachable && revision !== loadedRevision && !historyBusy) loadHistory();
  }
  $("history-mode").textContent = demo ? "Historial de demostración" : "Guardado en este PC";
  $("storage-warning").hidden = !next.storage_error;
  $("storage-warning").textContent = next.storage_error || "";
}
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const next = await api("/api/state", {timeout: 3000});
    failedPolls = 0; render(next);
  } catch {
    failedPolls++;
    if (!state || failedPolls >= 3) render({...state, connected: false, challenge: null, server_unreachable: true,
      message: "No hay conexión con la aplicación. Comprueba que la terminal siga abierta.", mode: state?.mode || "real"});
  } finally { polling = false; }
}

const eventLabels = {opened: "Apertura", closed: "Cierre", denied: "Rechazado", detected: "Detección", connection: "Conexión", info: "Sistema"};
async function loadHistory(force = false) {
  if (historyBusy && !force) return;
  const sequence = ++historySeq;
  const revision = state?.mode + ":" + state?.statistics?.revision;
  const params = new URLSearchParams({kind: historyFilter.kind, offset: String(historyOffset), limit: "20"});
  if (historyFilter.date) params.set("date", historyFilter.date);
  historyBusy = true;
  $("history-body").setAttribute("aria-busy", "true");
  try {
    const result = await api("/api/history?" + params);
    if (sequence !== historySeq) return;
    historyTotal = result.total;
    const body = $("history-body");
    body.replaceChildren();
    if (!result.events.length) {
      const row = document.createElement("tr"), cell = document.createElement("td");
      cell.colSpan = 3; cell.className = "history-empty"; cell.textContent = "No hay eventos con estos filtros.";
      row.append(cell); body.append(row);
    } else for (const event of result.events) {
      const row = document.createElement("tr"), when = document.createElement("td");
      const type = document.createElement("td"), detail = document.createElement("td"), badge = document.createElement("span");
      when.textContent = formatDate(event.created_at, {day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit"});
      badge.className = "event-badge"; badge.dataset.kind = event.kind;
      badge.textContent = eventLabels[event.kind] || "Sistema"; type.append(badge); detail.textContent = event.message;
      row.append(when, type, detail); body.append(row);
    }
    $("history-count").textContent = historyTotal ? (historyOffset + 1) + "–" + Math.min(historyOffset + 20, historyTotal) + " de " + historyTotal + " eventos" : "0 eventos";
    $("history-prev").disabled = historyOffset === 0;
    $("history-next").disabled = historyOffset + 20 >= historyTotal;
    loadedRevision = revision;
  } catch (error) {
    if (sequence === historySeq) $("history-count").textContent = "No se pudo cargar el historial. Reintentando…";
  } finally {
    if (sequence === historySeq) { historyBusy = false; $("history-body").setAttribute("aria-busy", "false"); }
  }
}
$("history-filters").addEventListener("submit", event => {
  event.preventDefault(); historyFilter = {kind: $("history-kind").value, date: $("history-date").value};
  historyOffset = 0; loadHistory(true);
});
$("history-reset").addEventListener("click", () => {
  $("history-kind").value = "all"; $("history-date").value = "";
  historyFilter = {kind: "all", date: ""}; historyOffset = 0; loadHistory(true);
});
$("history-prev").addEventListener("click", () => { historyOffset = Math.max(0, historyOffset - 20); loadHistory(true); });
$("history-next").addEventListener("click", () => {
  if (historyOffset + 20 < historyTotal) { historyOffset += 20; loadHistory(true); }
});

$("password-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (submitting || !state?.challenge) return;
  submitting = true; $("unlock-button").disabled = true; $("form-message").textContent = "Comprobando acceso…";
  try {
    await api("/api/unlock", {body: {password: $("password").value, challenge: state.challenge}});
    $("password").value = ""; dialog.close(); noticeOpen();
  } catch (error) {
    const message = messageFor(error);
    $("form-message").textContent = message; toast(message, "error"); playSound("error");
    $("password").value = ""; if (dialog.open) $("password").focus();
  } finally { submitting = false; $("unlock-button").disabled = false; await poll(); }
});
$("show-panel").addEventListener("click", showPanel);
$("close-panel").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => { $("password").value = ""; });
$("toggle-password").addEventListener("click", () => {
  const visible = $("password").type === "password";
  $("password").type = visible ? "text" : "password"; $("toggle-password").textContent = visible ? "Ocultar" : "Ver";
  $("toggle-password").setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
});
$("demo-toggle").addEventListener("click", async () => {
  try { render(await api("/api/demo/presence", {body: {present: !state?.present}})); }
  catch (error) { toast(messageFor(error), "error"); }
});

function lockAdmin(message = "") {
  adminAuthed = false; $("settings-gate").hidden = false; $("settings-content").hidden = true;
  $("admin-message").textContent = message;
  for (const id of ["admin-password", "current-password", "new-password", "confirm-password"]) $(id).value = "";
}
function fillSettings(settings) {
  applyPreferences(settings);
  $("setting-name").value = settings.name; $("setting-sound").checked = settings.sound_enabled;
  const passwordForm = $("change-password-form");
  for (const input of passwordForm.querySelectorAll("input,button")) input.disabled = !settings.password_change_allowed;
  $("password-help").textContent = settings.password_change_allowed ?
    "La contraseña sirve para abrir la puerta y entrar a la configuración." :
    "La contraseña está fijada por la variable CASA_PASSWORD del servidor.";
}
async function openSettings() {
  if (dialog.open) dialog.close();
  if (!settingsDialog.open) settingsDialog.showModal();
  $("admin-message").textContent = "Comprobando sesión…";
  try {
    const result = await api("/api/admin/session");
    fillSettings(result.settings);
    if (result.authenticated) {
      adminAuthed = true; $("settings-gate").hidden = true; $("settings-content").hidden = false;
    } else { lockAdmin(); $("admin-password").focus(); }
  } catch (error) { lockAdmin(messageFor(error)); }
}
$("settings-open").addEventListener("click", openSettings);
$("settings-close").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("close", () => {
  for (const id of ["admin-password", "current-password", "new-password", "confirm-password"]) $(id).value = "";
});
$("admin-login-form").addEventListener("submit", async event => {
  event.preventDefault(); if (adminBusy) return;
  adminBusy = true; const button = event.currentTarget.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    const result = await api("/api/admin/login", {body: {password: $("admin-password").value}});
    adminAuthed = true; fillSettings(result.settings);
    $("settings-gate").hidden = true; $("settings-content").hidden = false; $("admin-message").textContent = "";
  } catch (error) {
    $("admin-message").textContent = messageFor(error); toast(messageFor(error), "error"); playSound("error");
  } finally { $("admin-password").value = ""; adminBusy = false; button.disabled = false; await poll(); }
});
$("preferences-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.currentTarget.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    const result = await api("/api/settings", {body: {name: $("setting-name").value.trim(), sound_enabled: $("setting-sound").checked}});
    fillSettings(result.settings); $("preferences-message").textContent = ""; toast("Preferencias guardadas.", "success");
    await poll();
  } catch (error) {
    if (error.status === 401) lockAdmin(messageFor(error));
    else $("preferences-message").textContent = messageFor(error);
    toast(messageFor(error), "error");
  } finally { button.disabled = false; }
});
$("setting-sound").addEventListener("change", () => { if ($("setting-sound").checked) prepareAudio(true); });
$("sound-test").addEventListener("click", () => {
  prepareAudio(true);
  if (!audio) { toast("Este navegador no permite reproducir el aviso.", "error"); return; }
  audio.resume().then(() => playSound("success", true)).catch(() => toast("Permite el audio en tu navegador.", "error"));
});
$("change-password-form").addEventListener("submit", async event => {
  event.preventDefault();
  if ($("new-password").value !== $("confirm-password").value) {
    $("password-message").textContent = "Las contraseñas nuevas no coinciden."; return;
  }
  const button = event.currentTarget.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    await api("/api/settings/password", {body: {current_password: $("current-password").value,
      new_password: $("new-password").value, confirmation: $("confirm-password").value}});
    lockAdmin(); $("password-message").textContent = "";
    toast("Contraseña cambiada. Usa la nueva para el próximo acceso.", "success"); await poll();
  } catch (error) {
    if (error.status === 401 && error.message !== "Contraseña incorrecta") lockAdmin(messageFor(error));
    else $("password-message").textContent = messageFor(error);
    toast(messageFor(error), "error"); playSound("error");
  } finally {
    for (const id of ["current-password", "new-password", "confirm-password"]) $(id).value = "";
    button.disabled = state?.settings?.password_change_allowed === false;
  }
});
$("admin-logout").addEventListener("click", async () => {
  try { await api("/api/admin/logout", {body: {}}); lockAdmin(); toast("Sesión de configuración cerrada."); }
  catch (error) { toast(messageFor(error), "error"); }
});
poll();
setInterval(poll, 400);
