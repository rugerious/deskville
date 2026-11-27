// Deskville council site (layer 7, D46). Sign-in: Cognito hosted page, authorization
// code + PKCE. The ID token lives in memory only: reloading the page signs the resident
// out of this page (Cognito's own session makes signing back in quick).
import { COUNCILS, SERVICES, councilForHost } from "./councils.js";
import { CONFIG } from "./config.js";

const slug = councilForHost(location.hostname);
const council = COUNCILS[slug];
const home = `${location.origin}/`;
const $ = (id) => document.getElementById(id);
let idToken = null;
let online = false;

// ---- presentation for this council ------------------------------------------------
const rootStyle = document.documentElement.style;
rootStyle.setProperty("--ink", council.ink);
rootStyle.setProperty("--soft", council.soft);
if (council.artPosition) rootStyle.setProperty("--art-position", council.artPosition);
document.querySelectorAll("[data-council-name]").forEach((el) => { el.textContent = council.name; });
document.querySelectorAll("[data-council-site]").forEach((el) => { el.href = council.site; });
document.title = `Deskville ${council.name}: your town's front desk (unofficial demo)`;
Object.assign($("art"), { src: council.art, alt: council.artAlt });
$("art-title").textContent = council.artTitle;
$("art-credit").textContent = council.artCredit;
$("skyline").innerHTML = council.skyline;

const BIN = (hex) => `<svg viewBox="0 0 64 80" aria-hidden="true" focusable="false">
  <rect x="4" y="6" width="56" height="9" rx="2.5" fill="${hex}"/><path d="M8 17h48l-4 53H12z" fill="${hex}"/>
  <circle cx="17" cy="72" r="6" fill="#20262a"/><circle cx="47" cy="72" r="6" fill="#20262a"/></svg>`;
// The council's bin key lives in the "Bins and recycling" service: the facts at a glance,
// from the council's own collection page, even while the assistant is switched off.
const binKey = () => `<ul class="bin-key">${council.bins.map((b) =>
  `<li>${BIN(b.hex)}<span><strong>${b.colour}</strong> ${b.takes.toLowerCase()}, ${b.every}</span></li>`).join("")}</ul>
  <span class="bin-note">${council.putOut}</span>`;

const icon = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${d}</svg>`;
const ICONS = {
  bins: icon('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>'),
  tax: icon('<path d="M15 6.5A4 4 0 008.5 9v3H7m1.5 0H14M8.5 12v1.5c0 2-1 3.5-2.5 4.5H17"/>'),
  roads: icon('<path d="M5 16V11l2-4h10l2 4v5M5 16h14M7 16v2M17 16v2"/><circle cx="8" cy="13.5" r="1"/><circle cx="16" cy="13.5" r="1"/>'),
  requests: icon('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h3"/>'),
};
const ARROW = `<svg viewBox="0 0 24 24" focusable="false"><path d="M5 12h13M13 7l5 5-5 5"/></svg>`;

for (const s of SERVICES) {
  const li = document.createElement("li");
  const b = document.createElement("button");
  b.type = "button";
  b.className = "service";
  b.innerHTML = `<span class="service-icon">${ICONS[s.id]}</span><span class="service-text"><strong></strong><span></span></span><span class="service-go" aria-hidden="true">${ARROW}</span>`;
  b.querySelector("strong").textContent = s.title;
  b.querySelector(".service-text span").textContent = s.text;
  b.addEventListener("click", () => startQuestion(s.ask || council.request));
  li.append(b);
  if (s.id === "bins") {
    li.classList.add("service-wide");
    const key = document.createElement("div");
    key.className = "bin-panel";
    key.innerHTML = binKey();
    const more = document.createElement("a");
    more.href = council.binsSource; more.textContent = "Check your collection days on the council's site";
    key.append(more);
    li.append(key);
  }
  $("service-list").append(li);
}

function startQuestion(text) {
  $("q").value = text;
  $("ask").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  $("q").focus({ preventScroll: true });
}

// ---- small helpers ------------------------------------------------------------------
const b64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const randomString = () => b64url(crypto.getRandomValues(new Uint8Array(48)));
const claims = (jwt) => JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dateText = (iso) => iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : "";

function setStatus(text, tone = "") { $("status").textContent = text; $("status").dataset.tone = tone; }

function render() {
  const signedIn = Boolean(idToken);
  $("signin").hidden = signedIn;
  $("signout").hidden = !signedIn;
  $("who").hidden = !signedIn;
  if (!online) setStatus("The assistant is switched off right now. It runs only during demonstration sessions.", "off");
  else if (!signedIn) setStatus(`Sign in with a ${council.name} demo account to ask.`);
  else setStatus("");
}

// ---- sign-in: authorization code + PKCE ---------------------------------------------
async function signIn() {
  const verifier = randomString(), state = randomString();
  sessionStorage.setItem("pkce", JSON.stringify({ verifier, state })); // a one-time secret, not a token
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const url = new URL(`https://${CONFIG.loginDomain}/oauth2/authorize`);
  url.search = new URLSearchParams({ response_type: "code", client_id: CONFIG.clientId, redirect_uri: home,
    scope: "openid profile", state, code_challenge: b64url(digest), code_challenge_method: "S256" });
  location.assign(url);
}

async function finishSignIn() {
  const params = new URLSearchParams(location.search);
  const code = params.get("code");
  if (!code) return;
  history.replaceState(null, "", home); // the code is single-use; keep it out of history
  const saved = JSON.parse(sessionStorage.getItem("pkce") || "null");
  sessionStorage.removeItem("pkce");
  if (!saved || saved.state !== params.get("state")) { setStatus("Sign-in didn't complete. Sign in again.", "error"); return; }
  const r = await fetch(`https://${CONFIG.loginDomain}/oauth2/token`, { method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "authorization_code", client_id: CONFIG.clientId, code,
      redirect_uri: home, code_verifier: saved.verifier }) });
  if (!r.ok) { setStatus("Sign-in didn't complete. Sign in again.", "error"); return; }
  idToken = (await r.json()).id_token;
  const c = claims(idToken);
  const theirs = c["custom:tenant"];
  $("who").textContent = `${c.name || "Demo resident"}, ${COUNCILS[theirs]?.name || "unknown council"}`;
  if (theirs !== slug) {
    setStatus(`This account belongs to ${COUNCILS[theirs]?.name || "another council"}, so this site can't answer for it. Use ${theirs}.deskville.co.uk instead.`, "error");
  }
}

function signOut() {
  idToken = null;
  const url = new URL(`https://${CONFIG.loginDomain}/logout`);
  url.search = new URLSearchParams({ client_id: CONFIG.clientId, logout_uri: home });
  location.assign(url);
}

// ---- asking -------------------------------------------------------------------------
function answerHtml(text, count) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d+)\]/g, (m, n) => (n >= 1 && n <= count ? `<a class="cite" href="#source-${n}" aria-label="source ${n}">${n}</a>` : ""));
}

async function ask(event) {
  event.preventDefault();
  const question = $("q").value.trim();
  if (question.length < 3) { setStatus("Write your question first.", "error"); $("q").focus(); return; }
  if (!online) { render(); return; }
  if (!idToken) { setStatus(`Sign in with a ${council.name} demo account first. Your question stays in the box.`, "error"); $("signin").focus(); return; }
  $("send").disabled = true;
  setStatus("Looking it up in the council's pages…");
  try {
    const r = await fetch(`${CONFIG.api}/ask`, { method: "POST",
      headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ question }) });
    const body = await r.json().catch(() => ({}));
    if (r.status === 401) { idToken = null; render(); setStatus("Your sign-in has expired. Sign in again to ask.", "error"); return; }
    if (r.status === 403) { setStatus(`This account belongs to another council, so ${council.name}'s site can't answer for it.`, "error"); return; }
    if (!r.ok) { setStatus("The assistant couldn't answer just now. Try again in a minute.", "error"); return; }
    showAnswer(body);
    setStatus("");
  } catch {
    online = false; render();
  } finally {
    $("send").disabled = false;
  }
}

function showAnswer(body) {
  const sources = body.sources || [];
  $("answer").hidden = false;
  $("answer").dataset.blocked = body.blocked || "";
  $("answer-text").innerHTML = answerHtml(body.answer || "", sources.length);
  const tools = body.tools || [];
  $("answer-tools").hidden = tools.length === 0;
  $("answer-tools").textContent = tools.map((t) => `Looked up request ${t.reference}: ${t.found ? "found" : "not found for this council"}.`).join(" ");
  $("sources-title").hidden = sources.length === 0;
  $("answer-sources").innerHTML = sources.map((s) => {
    const link = (s.urls || [])[0];
    return `<li id="source-${s.n}"><span class="source-title">${escapeHtml(s.heading)}</span>
      ${link ? `<a href="${escapeHtml(link)}" rel="noopener">Read the council's page</a>` : ""}
      ${s.retrieved ? `<span class="source-date">checked ${dateText(s.retrieved)}</span>` : ""}</li>`;
  }).join("");
}

// ---- start --------------------------------------------------------------------------
async function checkOnline() {
  try {
    const r = await fetch(`${CONFIG.api}/health`, { signal: AbortSignal.timeout(4000) });
    online = r.ok;
  } catch { online = false; }
}

$("signin").addEventListener("click", signIn);
$("signout").addEventListener("click", signOut);
$("askform").addEventListener("submit", ask);
await Promise.all([finishSignIn(), checkOnline()]);
const keep = $("status").dataset.tone === "error" ? $("status").textContent : null;
render();
if (keep) setStatus(keep, "error");
