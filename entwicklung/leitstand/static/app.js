"use strict";
// Leitstand: fragt einmal je Sekunde den Server, zeichnet das Diagramm und die Formulare der Haltepunkte.
// Text von Agenten (Spec, Tests, Plan, Fragen) kommt nur über textContent ins DOM, nie als HTML.

const params = new URLSearchParams(location.search);
if (params.get("token")) {
  sessionStorage.setItem("leitstand-token", params.get("token"));
  history.replaceState(null, "", location.pathname + location.hash);  // Token nicht in der Adresszeile lassen
}
const TOKEN = sessionStorage.getItem("leitstand-token") || "";
const zustand = { laeufe: [], gewaehlt: decodeURIComponent(location.hash.slice(1)) || null, lauf: null,
                  graphen: {}, unterwegs: false, meldung: null, gezeichnet: null, formSchluessel: null,
                  rat: null, ratSchluessel: null, ratSeit: null, vorgefuellt: null, vorgefuelltText: null,
                  einwandSchluessel: null };

// ---------------------------------------------------------------------------------------------- Hilfen
function el(tag, attrs = {}, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kinder.flat()) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
async function api(pfad, optionen = {}) {
  const antwort = await fetch(pfad, { ...optionen, headers: { "X-Leitstand-Token": TOKEN,
    "Content-Type": "application/json", ...(optionen.headers || {}) } });
  let daten = null;
  try { daten = await antwort.json(); } catch (_) { /* leer */ }
  return { ok: antwort.ok, status: antwort.status, daten };
}
const fuelle = (ziel, ...kinder) =>  // replaceChildren machte aus null den Text „null“
  ziel.replaceChildren(...kinder.flat().filter((k) => k !== null && k !== undefined && k !== false));
const zeit = (iso) => iso ? new Date(iso).toLocaleTimeString("de-DE") : "";
const SYMBOL = { gruen: "🟢", rot: "🔴", grenzverletzung: "⛔", agent_fehler: "🟠", angenommen: "🟡",
                 abgebrochen: "⏹", akzeptanz_fehler: "⚠", wartet: "⏸", laeuft: "▶" };
function markenKlasse(status) {
  if (status === "wartet" || status === "angenommen") return "wartet";  // 🟡: kein Fehler, aber nicht grün
  if (status === "gruen") return "gruen";
  if (status === "laeuft" || status === "unbekannt") return "laeuft";
  return "schlecht";
}

// ---------------------------------------------------------------------------------------------- Liste
function zeichneListe() {
  const ziel = document.getElementById("laeufe");
  ziel.replaceChildren(...(zustand.laeufe.length ? zustand.laeufe.map((l) => {
    const status = l.zustand && l.zustand.laeuft ? "laeuft" : l.status;
    return el("div", { class: "lauf" + (l.thread_id === zustand.gewaehlt ? " gewaehlt" : ""),
                       onclick: () => waehle(l.thread_id) },
      el("div", { class: "kopf" }, el("span", { text: l.aufgabe_id || "?" }),
         el("span", { class: "marke " + markenKlasse(status), text: `${SYMBOL[status] || ""} ${status}` })),
      el("div", { class: "unter", text: `${l.thread_id} · Stufe ${l.stufe}` + (l.wartepunkt ? ` · ${l.wartepunkt}` : "")
                                         + (l.zustand && l.zustand.fehler ? " · Fehler" : "") }));
  }) : [el("div", { class: "leise", text: "Noch keine Läufe." })]));
}
function waehle(tid) {
  zustand.gewaehlt = tid;
  zustand.lauf = null;  // Formular des vorigen Laufs sofort weg, damit kein Klick dort landet
  zustand.meldung = null;
  zustand.formSchluessel = null;
  location.hash = encodeURIComponent(tid);
  zeichneListe();
  holeLauf();
}

// ---------------------------------------------------------------------------------------------- Diagramm
const B = 172, H = 38, DX = 196, DY = 64;
function zeichneDiagramm(graph, lauf) {
  const ebenen = Math.max(...graph.knoten.map((k) => k.ebene)) + 1;
  const breite = Math.max(...graph.knoten.map((k) => k.spalte)) + 1;
  const proEbene = {};
  graph.knoten.forEach((k) => { proEbene[k.ebene] = (proEbene[k.ebene] || 0) + 1; });
  const W = Math.max(breite * DX + 120, 600), HOEHE = ebenen * DY + 80;
  const pos = {};
  graph.knoten.forEach((k) => {
    const n = proEbene[k.ebene];
    pos[k.id] = { x: W / 2 + (k.spalte - (n - 1) / 2) * DX, y: 60 + k.ebene * DY };
  });
  const svg = svgEl("svg", { width: W, height: HOEHE, viewBox: `0 0 ${W} ${HOEHE}` });
  const defs = svgEl("defs");
  const pfeil = svgEl("marker", { id: "pfeil", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7,
                                  orient: "auto-start-reverse" });
  pfeil.append(svgEl("path", { d: "M0,0 L10,5 L0,10 z", fill: "#3a4c66" }));
  defs.append(pfeil);
  svg.append(defs);
  const erledigt = new Set(lauf ? lauf.erledigt : []);
  const aktiv = new Set(lauf ? lauf.aktiv : []);
  // gegangene Kanten aus aufeinanderfolgenden Schritten des Verlaufs (nicht aus „beide Enden erledigt“)
  const schritte = lauf ? lauf.verlauf.map((v) => v.knoten) : [];
  if (lauf && lauf.wartepunkt) schritte.push([lauf.wartepunkt]);
  else if (lauf && lauf.aktiv.length) schritte.push(lauf.aktiv);
  const gegangeneKanten = new Set();
  for (let i = 0; i + 1 < schritte.length; i++)
    for (const a of schritte[i]) for (const b of schritte[i + 1]) gegangeneKanten.add(a + ">" + b);
  for (const k of graph.kanten) {
    const a = pos[k.von], b = pos[k.nach];
    if (!a || !b) continue;
    let d;
    if (k.von === k.nach) {  // Kante zu sich selbst (ungültige Antwort: noch einmal fragen)
      d = `M${a.x + B / 2},${a.y - 6} C${a.x + B / 2 + 40},${a.y - 30} ${a.x + B / 2 + 40},${a.y + 30} ${a.x + B / 2},${a.y + 6}`;
    } else if (k.zurueck) {  // Rückkante seitlich vorbei
      const seite = Math.max(a.x, b.x) + B / 2 + 26 + Math.abs(a.y - b.y) / 14;
      d = `M${a.x + B / 2},${a.y} C${seite},${a.y} ${seite},${b.y} ${b.x + B / 2},${b.y}`;
    } else {
      d = `M${a.x},${a.y + H / 2} C${a.x},${(a.y + b.y) / 2} ${b.x},${(a.y + b.y) / 2} ${b.x},${b.y - H / 2 - 2}`;
    }
    const gegangen = gegangeneKanten.has(k.von + ">" + k.nach);
    svg.append(svgEl("path", { d, class: "e" + (k.bedingt ? " bedingt" : "") + (k.zurueck ? " zurueck" : "")
                                       + (k.abbruch ? " abbruch" : "") + (gegangen ? " gegangen" : ""),
                               "marker-end": "url(#pfeil)" }));
  }
  for (const k of graph.knoten) {
    const { x, y } = pos[k.id];
    const klassen = ["k", k.phase];
    if (erledigt.has(k.id)) klassen.push("erledigt");
    if (aktiv.has(k.id)) klassen.push("aktiv");
    if (lauf && lauf.wartepunkt === k.id) klassen.push("wartet");
    const g = svgEl("g", { class: klassen.join(" ") });
    if (k.haltepunkt) {
      g.append(svgEl("polygon", { points: `${x - B / 2},${y} ${x - B / 2 + 14},${y - H / 2} ${x + B / 2 - 14},${y - H / 2} ${x + B / 2},${y} ${x + B / 2 - 14},${y + H / 2} ${x - B / 2 + 14},${y + H / 2}` }));
    } else {
      g.append(svgEl("rect", { x: x - B / 2, y: y - H / 2, width: B, height: H, rx: k.phase === "rand" ? 19 : 7 }));
    }
    const t = svgEl("text", { x, y });
    t.textContent = (k.haltepunkt ? "◆ " : "") + k.id.replace(/^__|__$/g, "");
    g.append(t);
    const titel = svgEl("title");
    titel.textContent = k.text || k.id;
    g.append(titel);
    svg.append(g);
  }
  document.getElementById("svgplatz").replaceChildren(svg);
}
async function zeichneGraph() {
  const stufe = zustand.lauf ? zustand.lauf.stufe : 4;
  if (!zustand.graphen[stufe]) {
    const r = await api(`/api/graph?stufe=${stufe}`);
    if (!r.ok) return;
    zustand.graphen[stufe] = r.daten;
  }
  const schluessel = JSON.stringify([stufe, zustand.lauf && [zustand.lauf.erledigt, zustand.lauf.aktiv, zustand.lauf.wartepunkt]]);
  if (schluessel === zustand.gezeichnet) return;  // nichts geändert: nicht neu zeichnen (Animation läuft weiter)
  zustand.gezeichnet = schluessel;
  zeichneDiagramm(zustand.graphen[stufe], zustand.lauf);
}

// ---------------------------------------------------------------------------------------------- Details
function punkteListe(punkte) {
  if (!punkte || !punkte.length) return el("div", { class: "leise", text: "keine Punkte" });
  return el("ul", { class: "punkte" }, punkte.map((p) => el("li", { text: `[${p.pruefer}, ${p.schwere}] ${p.aussage}` })));
}
function punktMarke(p) {
  // 6c: neue Punkte mit Herkunft, alte mit Status (wie konvergenz.punkt_zeile)
  return `[${p.pruefer}, ${p.schwere}, ${p.status ? `alt ${p.status}` : p.herkunft}] ${p.aussage}`;
}
function einordnungBlock(f) {
  // ab der Nachprüfung (6c): was eine neue Runde auslöst, was nur auf die Liste gehört, und der Verlauf je Fassung
  const e = f.einordnung || {};
  const gruppe = (punkte) => (punkte && punkte.length)
    ? el("ul", { class: "punkte" }, punkte.map((p) => el("li", { text: punktMarke(p) })))
    : el("div", { class: "leise", text: "keine" });
  const verlauf = el("table", { class: "stufen" },
    el("tr", {}, ...["Fassung", "Zeichen", "Annahmen", "Tests", "auslösend", "Liste"].map((k) => el("th", { text: k }))),
    ...(f.verlauf || []).map((v) => el("tr", {},
      el("td", { text: `${v.fassung}${v.nachgebessert ? " (Tests nachgebessert)" : ""}` }),
      ...[v.zeichen, v.annahmen, v.tests, v.ausloesend, v.liste].map((x) => el("td", { text: String(x) })))));
  return el("div", {},
    el("h2", { text: "Lösen eine neue Runde aus" }), gruppe(e.ausloesend),
    el("h2", { text: "Liste für dich (keine neue Runde nötig)" }), gruppe(e.liste),
    el("h2", { text: "Verlauf" }), verlauf);
}
function aufklappen(titel, text, offen = false) {
  return el("details", { open: offen }, el("summary", { text: titel }), el("pre", { text: text || "(leer)" }));
}
async function sende(body, stand = null) {
  // an den angezeigten Lauf, mit angezeigtem Haltepunkt und Stand (oder dem des Rats): der Server lehnt ab, wenn sich
  // etwas geändert hat
  const lauf = zustand.lauf;
  if (!lauf || lauf.thread_id !== zustand.gewaehlt) return;
  const mit = begruendungFuer(body);
  if (mit === null) {
    zustand.meldung = { ok: false, text: "Es gibt einen Einwand: Bitte oben begründen, warum du trotzdem durchlässt." };
    zeichneMeldung();
    document.getElementById("begruendung")?.focus();
    return;
  }
  body = mit;
  zustand.unterwegs = true;
  zeichneDetails();
  const r = await api(`/api/laeufe/${encodeURIComponent(lauf.thread_id)}/antwort`, { method: "POST",
    body: JSON.stringify({ ...body, haltepunkt: stand ? stand.haltepunkt : lauf.wartepunkt,
                           checkpoint_id: stand ? stand.checkpoint_id : lauf.checkpoint_id }) });
  zustand.unterwegs = false;
  zustand.meldung = r.ok ? { ok: true, text: "Gesendet. Der Lauf arbeitet weiter …" }
    : { ok: false, text: (r.daten && r.daten.fehler || `Fehler ${r.status}`)
                         + (r.daten && r.daten.erlaubt ? ` · erlaubt: ${r.daten.erlaubt.join(", ")}` : "") };
  if (r.ok) { const feld = document.getElementById("begruendung"); if (feld) feld.value = ""; }
  zustand.formSchluessel = null;
  await holeLauf();
}
function knopf(text, klasse, aktion, braucht = null) {
  const gesperrt = zustand.unterwegs || (zustand.lauf && zustand.lauf.zustand.laeuft);
  return el("button", { class: klasse, disabled: gesperrt, text, onclick: () => {
    const hinweis = document.getElementById("hinweis");
    if (braucht && !(hinweis && hinweis.value.trim())) {
      zustand.meldung = { ok: false, text: `Für „${text}“ bitte einen Hinweis eintragen.` };
      zeichneMeldung();
      return;
    }
    aktion(hinweis ? hinweis.value.trim() : "");
  } });
}
function formular(lauf) {
  const f = lauf.frage;
  const karte = el("div", { class: "karte halt" });
  if (f.hinweis) karte.append(el("div", { class: "meldung fehler", text: f.hinweis }));
  if (lauf.wartepunkt === "fragen") {
    karte.append(el("h3", { text: `⏸ Rückfragen (Runde ${f.runde} von ${f.max_runden})` }),
      el("div", { class: "leise", text: f.verstaendnis }),
      el("ol", { class: "punkte" }, f.fragen.map((q) => el("li", { text: q }))),
      el("label", { for: "antwort", text: "Deine Antworten (alle in einem Text)" }), el("textarea", { id: "antwort" }),
      el("div", { class: "knoepfe" },
        knopf("Antwort senden", "haupt", () => {
          const text = document.getElementById("antwort").value.trim();
          if (!text) { zustand.meldung = { ok: false, text: "Bitte eine Antwort eintragen." }; zeichneMeldung(); return; }
          sende({ antwort: text });
        }),
        knopf("Abbrechen", "gefahr", () => sende({ entscheidung: "abbrechen" }))));
  } else if (lauf.wartepunkt === "spec_freigabe") {
    const p = f.probe || {};
    karte.append(el("h3", { text: `⏸ Spec-Freigabe (Fassung ${f.spec_runde + 1})` }),
      el("div", { class: "leise", text: `Probe: ${p.erwartet - p.bestanden} von ${p.erwartet} Tests rot gegen main` }),
      aufklappen("Spec lesen", f.spec_text, true),
      ...Object.entries(f.tests_text || {}).map(([name, inhalt]) => aufklappen(`Tests: ${name} (${f.tests.length})`, inhalt)),
      el("h2", { text: "Annahmen" }), el("ul", { class: "punkte" }, (f.annahmen || []).map((a) => el("li", { text: a }))),
      ...(f.nachpruefung && f.einordnung ? [einordnungBlock(f)]
        : [el("h2", { text: "Punkte der Spec-Prüfer" }), punkteListe(f.pruefpunkte)]),
      ...(f.nicht_verwertbar || []).map((n) => el("div", { class: "meldung fehler", text: `nicht verwertbar: ${n}` })),
      el("label", { for: "hinweis", text: "Hinweis (für „ändern“ und „Tests nachbessern“)" }), el("textarea", { id: "hinweis" }),
      el("div", { class: "knoepfe" },
        knopf("Freigeben", "haupt", () => sende({ entscheidung: "freigeben" })),
        knopf("Spec ändern", "", (h) => sende({ entscheidung: "aendern", hinweis: h }), true),
        knopf("Tests nachbessern", "", (h) => sende({ entscheidung: "tests_nachbessern", hinweis: h }), true),
        knopf("Abbrechen", "gefahr", () => sende({ entscheidung: "abbrechen" }))));
  } else if (lauf.wartepunkt === "plan_freigabe") {
    karte.append(el("h3", { text: `⏸ Plan-Freigabe (Fassung ${f.plan_runde + 1})` }),
      aufklappen("Plan lesen", f.plan_text, true),
      el("div", { class: "leise", text: `Dateien: ${(f.dateien || []).join(", ") || "–"}` }),
      el("h2", { text: "Punkte (Code und Codex)" }), punkteListe(f.pruefpunkte),
      ...(f.nicht_verwertbar || []).map((n) => el("div", { class: "meldung fehler", text: `nicht verwertbar: ${n}` })),
      stufenBlock(f),
      el("label", { for: "hinweis", text: "Hinweis (für „ändern“)" }), el("textarea", { id: "hinweis" }),
      el("div", { class: "knoepfe" },
        knopf("Freigeben", "haupt", () => sende({ entscheidung: "freigeben",
                                                 ...(f.tabelle ? { komplexitaet: document.getElementById("komplexitaet").value } : {}) })),
        knopf("Plan ändern", "", (h) => sende({ entscheidung: "aendern", hinweis: h }), true),
        knopf("Abbrechen", "gefahr", () => sende({ entscheidung: "abbrechen" }))));
  } else if (lauf.wartepunkt === "abschluss_freigabe") {
    // Stufe 7: letzter Haltepunkt. Tür-Zeile direkt unter der Überschrift, einseitig rot mit Fallliste
    const t = f.tuer || {};
    const g = f.gesamtreview || {};
    const d = g.daten || {};
    const faelle = t.faelle || [];
    karte.append(...[el("h3", { text: `⏸ Abschluss-Freigabe (${f.status})` }),
      el("div", { class: "tuer" + (t.urteil === "einseitig" ? " einseitig" : ""), text: f.tuer_zeile }),
      faelle.length ? el("ul", { class: "punkte" }, faelle.map((x) => el("li", { text: `einseitig: ${x}` }))) : null,
      el("div", { class: "leise", text: `${f.tests_zeile} (${f.tests})` }),
      el("h2", { text: "Gesamtreview (Codex)" }),
      g.ok ? el("div", { text: `${d.verdict} · Spec erfüllt: ${d.spec_erfuellt ? "ja" : "nein"} · ${d.zusammenfassung || ""}` })
        : el("div", { class: "meldung fehler", text: `nicht verwertbar: ${g.fehler || "nicht gelaufen"}` }),
      el("ul", { class: "punkte" }, (d.restpunkte || []).map((p) => el("li", { text: `[${p.schwere}] ${p.aussage}` }))),
      el("div", { class: "leise", text: `Branch ${f.branch} → ${f.zielzweig || "?"} (nur Fast-Forward, kein Push)` }),
      aufklappen("Diffstat", f.diffstat),
      (f.offene_befunde || []).length ? aufklappen(`Offene Befunde (${f.offene_befunde.length})`,
        f.offene_befunde.map((b) => `[${b.severity}/${b.kind}] ${b.path}:${b.line} — ${b.claim}`).join("\n")) : null,
      el("div", { class: "leise", text: `Akzeptanztests übernehmen nach ${f.uebernahme_ziel} (nicht committet)` }),
      el("div", { class: "knoepfe" },
        knopf("Mergen", "haupt", () => sende({ entscheidung: "mergen" })),
        knopf("Nicht mergen", "gefahr", () => sende({ entscheidung: "nicht_mergen" })))]
      .filter(Boolean));  // append(null) schriebe „null“ in die Karte
  } else if (lauf.wartepunkt && lauf.wartepunkt.startsWith("budget")) {
    karte.append(el("h3", { text: "⏸ Kostenrahmen erreicht" }),
      el("div", { text: `${f.aufrufe} von ${f.budget} Agentenaufrufen verbraucht. Als Nächstes käme: ${f.naechster}.` }),
      el("div", { class: "leise", text: "Berater zählen nicht mit. „Mehr erlauben“ hebt den Rahmen an, der Lauf geht weiter." }),
      el("div", { class: "knoepfe" },
        knopf(`Mehr erlauben (+${f.schritt || 20})`, "haupt", () => sende({ entscheidung: "mehr" })),
        knopf("Abbrechen", "gefahr", () => sende({ entscheidung: "abbrechen" }))));
  } else if (lauf.wartepunkt === "eskalation") {
    karte.append(el("h3", { text: `⏸ Eskalation (Runde ${f.runde} von höchstens ${f.max_runden})` }),
      el("div", { text: f.frage }), el("div", { class: "leise", text: `Tests: ${f.tests}` }),
      el("ul", { class: "punkte" }, (f.ausloesend || []).map((b) =>
        el("li", { text: `[${b.severity}/${b.kind}] ${b.path}:${b.line} — ${b.claim} (${b.pruefer.join(", ")})` }))),
      el("div", { class: "knoepfe" },
        knopf("Weiter (eine Runde mehr)", "haupt", () => sende({ entscheidung: "weiter" })),
        knopf("Annehmen", "", () => sende({ entscheidung: "annehmen" })),
        knopf("Abbrechen", "gefahr", () => sende({ entscheidung: "abbrechen" }))));
  }
  return karte;
}
function stufenBlock(f) {
  // Modellstufen (6b-2): beide Schätzungen, das Ergebnis, und was die gewählte Komplexität für jede Rolle heißt
  if (!f.tabelle) return null;
  const auswahl = el("select", { id: "komplexitaet" },
    (f.komplexitaeten || Object.keys(f.tabelle)).map((k) => el("option", { value: k, text: k, selected: k === f.komplexitaet })));
  const tabelle = el("table", { class: "stufen" });
  const zeichne = () => fuelle(tabelle,
    el("tr", {}, el("th", { text: "Rolle" }), el("th", { text: "Modell" }), el("th", { text: "Reasoning" })),
    Object.entries(f.tabelle[auswahl.value] || {}).map(([rolle, s]) =>
      el("tr", {}, el("td", { text: rolle }), el("td", { text: s.modell }), el("td", { text: s.effort }))));
  auswahl.addEventListener("change", zeichne);
  zeichne();
  const uneinig = f.komplexitaet_claude && f.komplexitaet_codex && f.komplexitaet_claude !== f.komplexitaet_codex;
  return el("div", { class: "karte stufe" + (uneinig ? " uneinig" : "") },
    el("h2", { text: "Modellstufe" }),
    el("div", { text: `Schätzung Claude: ${f.komplexitaet_claude || "–"} · Codex: ${f.komplexitaet_codex || "–"} → `
                      + `${f.komplexitaet} (die höhere gilt)` + (uneinig ? " · die Familien sind uneinig" : "") }),
    f.komplexitaet_grund ? el("div", { class: "leise", text: `Grund (Claude): ${f.komplexitaet_grund}` }) : null,
    f.komplexitaet_hinweis ? el("div", { class: "leise", text: f.komplexitaet_hinweis }) : null,
    el("label", { for: "komplexitaet", text: "Komplexität (der einzige Regler: Modell und Reasoning folgen der Tabelle)" }),
    auswahl, tabelle);
}
function zeichneMeldung() {
  const ziel = document.getElementById("meldung");
  if (!ziel) return;
  ziel.replaceChildren(...(zustand.meldung ? [el("div", { class: "meldung " + (zustand.meldung.ok ? "ok" : "fehler"),
                                                         text: zustand.meldung.text })] : []));
}
function zeichneDetails() {
  const lauf = zustand.lauf, ziel = document.getElementById("details");
  if (!TOKEN) {
    ziel.replaceChildren(el("div", { class: "meldung fehler",
      text: "Kein Zugangsschlüssel. Bitte den Leitstand über den Link öffnen, den „python -m entwicklung leitstand“ "
            + "ausgibt (oder über leitstand.cmd)." }));
    return;
  }
  if (!lauf) { ziel.replaceChildren(el("div", { id: "leer", text: "Links einen Lauf wählen oder einen neuen starten." })); return; }
  const status = lauf.zustand.laeuft ? "laeuft" : lauf.status;
  // Formular nur neu bauen, wenn sich der Haltepunkt ändert: sonst verlöre man beim Tippen den Text
  const schluessel = JSON.stringify([lauf.thread_id, lauf.wartepunkt, lauf.frage && lauf.frage.hinweis,
                                     lauf.zustand.laeuft, zustand.unterwegs]);
  if (schluessel === zustand.formSchluessel) { zeichneKopf(lauf, status); zeichneMeldung(); zeichneEinwand(); return; }
  zustand.formSchluessel = schluessel;
  zustand.einwandSchluessel = null;
  const t = lauf.testergebnis;
  fuelle(ziel,
    el("div", { id: "kopf" }), el("div", { id: "meldung" }),
    lauf.zustand.fehler ? el("div", { class: "meldung fehler", text: `Lauf abgestürzt: ${lauf.zustand.fehler}` }) : null,
    lauf.wartepunkt && lauf.frage ? el("div", { id: "ratplatz" }) : null,
    lauf.wartepunkt && lauf.frage ? el("div", { id: "einwandplatz" }) : null,
    lauf.wartepunkt && lauf.frage ? formular(lauf) : null,
    t ? el("div", { class: "karte" }, el("h3", { text: "Tests" }),
           el("div", { class: "leise", text: `${t.bestanden}/${t.gesammelt} bestanden · Akzeptanz ${t.akzeptanz.bestanden}/${t.akzeptanz.gesammelt}` })) : null,
    lauf.bericht_pfad ? el("div", { class: "karte" }, el("h3", { text: "Bericht" }), el("pre", { text: lauf.bericht_pfad })) : null,
    el("h2", { text: "Verlauf" }),
    el("div", { class: "verlauf" }, [...lauf.verlauf].reverse().map((v) => el("div", { text: `${zeit(v.zeit)}  ${v.knoten.join(", ")}` }))));
  zeichneKopf(lauf, status);
  zeichneMeldung();
  zeichneEinwand();
}
function zeichneKopf(lauf, status) {
  const kopf = document.getElementById("kopf");
  if (!kopf) return;
  kopf.replaceChildren(el("div", { class: "karte" },
    el("h3", { text: `${lauf.aufgabe_id || "?"} · ${lauf.thread_id}` }),
    el("span", { class: "marke " + markenKlasse(status), text: `${SYMBOL[status] || ""} ${status}` }),
    el("span", { class: "leise", text: `  Stufe ${lauf.stufe}` + (lauf.runde !== null && lauf.runde !== undefined ? ` · Runde ${lauf.runde}` : "")
                                       + (lauf.budget ? ` · Aufrufe ${lauf.aufrufe}/${lauf.budget}` : "")
                                       + (lauf.aktiv.length ? ` · gerade: ${lauf.aktiv.join(", ")}` : "") })));
}

// ---------------------------------------------------------------------------------------------- Start
async function startformular() {
  const form = document.getElementById("startform");
  form.hidden = !form.hidden;
  if (form.hidden) return;
  const r = await api("/api/start-optionen");
  if (!r.ok) return;
  const o = r.daten;
  const fuelle = (id, werte, standard) => document.getElementById(id).replaceChildren(
    ...werte.map((w) => el("option", { value: w, text: w, selected: String(w) === String(standard) })));
  fuelle("s-repo", Object.keys(o.repos), "portwart");
  const aufgaben = () => fuelle("s-aufgabe", o.repos[document.getElementById("s-repo").value] || [], "");
  document.getElementById("s-repo").onchange = aufgaben;
  aufgaben();
  fuelle("s-stufe", o.stufen, 4);
  fuelle("s-modell", o.modelle, "auto");  // auto: Modell und Reasoning nach Komplexität (Tabelle)
  fuelle("s-pruefer", o.modelle, "auto");
  document.getElementById("s-budget").value = o.budget || 40;
}
async function starten() {
  const wert = (id) => document.getElementById(id).value;
  const knopf = document.getElementById("starten");
  knopf.disabled = true;
  const r = await api("/api/laeufe", { method: "POST", body: JSON.stringify({ repo: wert("s-repo"), aufgabe: wert("s-aufgabe"),
    stufe: Number(wert("s-stufe")), modell: wert("s-modell"), pruefer_modell: wert("s-pruefer"),
    budget: Number(wert("s-budget")) }) });
  knopf.disabled = false;
  const ziel = document.getElementById("startmeldung");
  if (!r.ok) { ziel.replaceChildren(el("div", { class: "meldung fehler", text: (r.daten && r.daten.fehler) || `Fehler ${r.status}` })); return; }
  ziel.replaceChildren();
  document.getElementById("startform").hidden = true;
  await holeListe();
  waehle(r.daten.thread_id);
}

// ---------------------------------------------------------------------------------------------- Schleife
async function holeListe() {
  const r = await api("/api/laeufe");
  document.getElementById("verbindung").classList.toggle("aus", !r.ok);
  if (!r.ok) return;
  zustand.laeufe = r.daten;
  zeichneListe();
}
async function holeLauf() {
  if (!zustand.gewaehlt) { zustand.lauf = null; zeichneDetails(); await zeichneGraph(); return; }
  const gefragt = zustand.gewaehlt;
  const r = await api(`/api/laeufe/${encodeURIComponent(gefragt)}`);
  if (gefragt !== zustand.gewaehlt) return;  // inzwischen anderer Lauf gewählt: verspätete Antwort verwerfen
  const vorher = zustand.lauf;
  zustand.lauf = r.ok ? r.daten : null;
  const neu = zustand.lauf;  // neuer Haltepunkt oder Ende: die Meldung zur vorigen Antwort gilt nicht mehr
  if (vorher && neu && vorher.thread_id === neu.thread_id && !neu.zustand.laeuft
      && (vorher.wartepunkt !== neu.wartepunkt || vorher.status !== neu.status)) zustand.meldung = null;
  zeichneDetails();
  await holeRat();
  await zeichneGraph();
}
function verbindungWeg(weg) {
  // Server beendet (Fenster geschlossen): deutlich sagen und nichts mehr anklickbar lassen, statt ins Leere zu klicken
  document.getElementById("verbindung").classList.toggle("aus", weg);
  let hinweis = document.getElementById("getrennt");
  if (weg && !hinweis) {
    hinweis = el("div", { id: "getrennt", class: "meldung fehler",
      text: "Keine Verbindung zum Leitstand-Server. Läuft er noch? (Leitstand neu starten, z. B. über leitstand.cmd.)" });
    document.getElementById("details").prepend(hinweis);
    document.querySelectorAll("#details button").forEach((b) => { b.disabled = true; });
  } else if (!weg && hinweis) {
    hinweis.remove();
    zustand.formSchluessel = null;  // Formular neu aufbauen, Knöpfe wieder frei
  }
}
async function takt() {
  try {
    await holeListe();
    await holeLauf();
    verbindungWeg(false);
  } catch (e) {
    verbindungWeg(true);
  }
  document.getElementById("uhr").textContent = new Date().toLocaleTimeString("de-DE");
}
document.getElementById("neu").addEventListener("click", startformular);
document.getElementById("startabbruch").addEventListener("click", () => { document.getElementById("startform").hidden = true; });
document.getElementById("starten").addEventListener("click", starten);
api("/api/info").then((r) => {  // Demo mit Fake-Agenten unübersehbar kennzeichnen
  if (r.ok && r.daten.demo) {
    document.body.classList.add("demo");
    document.querySelector("header h1").after(el("span", { class: "demo-marke", text: "DEMO – Fake-Agenten, keine echten Läufe" }));
    document.title = "DEMO · Leitstand";
  }
});
takt();
setInterval(takt, 1000);

// ---------------------------------------------------------------------------------------------- Berater (Fable, Astra)
// Fable (Claude) und Astra (Codex, GPT-Familie) beraten, Dominic entscheidet: Der Rat füllt das Formular vor;
// abgeschickt wird erst mit „Empfehlung übernehmen“. Sind sie uneinig, ist die vorsichtigere Empfehlung vorbelegt.
const EMPFEHLUNG = { antwort: "Antworten", abbrechen: "Abbrechen", freigeben: "Freigeben", aendern: "Ändern",
                     tests_nachbessern: "Tests nachbessern", weiter: "Weiter", annehmen: "Annehmen",
                     mehr: "Mehr erlauben" };
const BERATER = {
  fable: { name: "Fable", zeichen: "🧠", unter: "Claude-Familie, liest das Repo selbst" },
  astra: { name: "Astra", zeichen: "🛰️", unter: "GPT-Familie, liest nur Eingebettetes" },
};
async function holeRat() {
  const lauf = zustand.lauf;
  if (!lauf || !lauf.wartepunkt || amRahmen(lauf)) { zustand.rat = null; zeichneRat(); return; }
  const r = await api(`/api/laeufe/${encodeURIComponent(lauf.thread_id)}/rat`);
  if (lauf !== zustand.lauf) return;  // inzwischen anderer Lauf
  // 204: noch kein Rat. Ein Rat zu einem anderen Haltepunkt gehört nicht hierher (nur „veraltet“ bei gleichem Haltepunkt)
  const passt = (e) => (e && e.haltepunkt === lauf.wartepunkt ? e : null);
  zustand.rat = r.ok && r.daten ? { fable: passt(r.daten.fable), astra: passt(r.daten.astra),
                                     vergleich: r.daten.vergleich } : null;
  zeichneRat();
}
async function frageRat(wer) {
  const lauf = zustand.lauf;
  zustand.ratSeit = Date.now();
  const r = await api(`/api/laeufe/${encodeURIComponent(lauf.thread_id)}/rat?wer=${wer}`, { method: "POST" });
  if (!r.ok) { zustand.meldung = { ok: false, text: (r.daten && r.daten.fehler) || `Fehler ${r.status}` }; zeichneMeldung(); }
  await holeRat();
}
function mitEigenemText(rat) {
  // Was im Feld steht, gilt: Hat Dominic den vorgeschlagenen Text geändert, geht seine Fassung mit (Codex F-006)
  const feld = document.getElementById(rat.haltepunkt === "fragen" ? "antwort" : "hinweis");
  const text = feld && feld.value.trim();
  if (!text) return rat.antwort;
  if ("antwort" in rat.antwort) return { ...rat.antwort, antwort: text };
  if ("hinweis" in rat.antwort) return { ...rat.antwort, hinweis: text };
  return rat.antwort;
}
function mitKomplexitaet(antwort, haltepunkt) {
  // An der Plan-Freigabe gilt der Regler auch beim Übernehmen einer Empfehlung „freigeben“ (Codex 6b-2: sonst
  // blieb eine im Formular geänderte Komplexität still unberücksichtigt).
  const regler = document.getElementById("komplexitaet");
  if (haltepunkt !== "plan_freigabe" || !regler || !antwort || antwort.entscheidung !== "freigeben") return antwort;
  return { ...antwort, komplexitaet: regler.value };
}
function vorfuellen(rat) {
  // einmal je Rat: Antwort- oder Hinweistext ins Formular, damit Dominic ihn ändern kann. Steht noch der Text eines
  // anderen Rats unverändert im Feld (z. B. Fable war schneller, vorbelegt ist Astra), wird er ersetzt; was Dominic
  // selbst geändert hat, bleibt (Codex 6b-1 F-003).
  const schluessel = rat.datei || rat.checkpoint_id;
  if (!rat.rat || zustand.vorgefuellt === schluessel || rat.veraltet) return;
  const feld = document.getElementById(rat.haltepunkt === "fragen" ? "antwort" : "hinweis");
  if (!feld) return;
  const automatisch = zustand.vorgefuelltText !== null && feld.value === zustand.vorgefuelltText;
  if (feld.value.trim() && !automatisch) return;
  feld.value = rat.rat.text || "";
  zustand.vorgefuellt = schluessel;
  zustand.vorgefuelltText = feld.value;
}
function sekundenText(sekunden) {
  return sekunden !== null ? `seit ${Math.floor(sekunden / 60)}:${String(sekunden % 60).padStart(2, "0")} min` : "";
}
function ratKarte(wer, rat, uebernehmbar, gesperrt, sekunden) {
  const b = BERATER[wer];
  const kopf = (text) => el("h3", {}, `${b.zeichen} ${b.name}${text}`, el("span", { class: "leise", text: `  ${b.unter}` }));
  if (rat.zustand === "laeuft") {
    return el("div", { class: `karte rat ${wer}` }, kopf(" denkt …"),
              el("div", { class: "leise", text: `${sekundenText(sekunden)} (dauert meist 1–5 min)` }));
  }
  const karte = el("div", { class: `karte rat ${wer}` + (rat.veraltet ? " veraltet" : "") });
  if (rat.zustand === "fehler" || rat.fehler) {
    karte.append(kopf(": kein Rat"), el("div", { class: "meldung fehler", text: rat.fehler || "Fehler" }));
    return karte;
  }
  const r = rat.rat;
  karte.append(el("h3", {}, `${b.zeichen} ${b.name} empfiehlt: `,
      el("span", { class: "marke empfehlung", text: EMPFEHLUNG[r.entscheidung] || r.entscheidung }),
      el("span", { class: "leise", text: `  Sicherheit: ${r.sicherheit} · ${b.unter}` })),
    el("div", { text: r.begruendung }));
  if (r.text) karte.append(el("label", { text: rat.haltepunkt === "fragen" ? "Vorgeschlagene Antwort" : "Vorgeschlagener Hinweis" }),
                           el("pre", { text: r.text }));
  if (r.punkte && r.punkte.length)
    karte.append(el("ul", { class: "punkte" }, r.punkte.map((p) =>
      el("li", { class: "punkt-" + p.einschaetzung, text: `[${{ echt: "echt", klein: "klein", falscher_alarm: "falscher Alarm" }[p.einschaetzung] || p.einschaetzung}] ${p.aussage} — ${p.warum}` }))));
  let grund = null;
  if (rat.veraltet) grund = "Veraltet: Der Lauf steht inzwischen woanders. Bitte neu fragen.";
  else if (!rat.antwort) grund = `Nicht verwertbar: ${rat.grund}`;
  if (uebernehmbar)
    karte.append(el("div", { class: "knoepfe" },
      el("button", { class: "haupt", disabled: gesperrt || !!grund, text: "Empfehlung übernehmen",
                     onclick: () => sende(mitKomplexitaet(mitEigenemText(rat), rat.haltepunkt),
                                          { haltepunkt: rat.haltepunkt, checkpoint_id: rat.checkpoint_id }) })));
  if (grund) karte.append(el("div", { class: "meldung fehler", text: grund }));
  return karte;
}
// kein Rat am Kostenrahmen (6b-2) und am Abschluss (Stufe 7: das Gesamtreview ist schon die Zweitmeinung)
const amRahmen = (lauf) => (lauf.wartepunkt || "").startsWith("budget") || lauf.wartepunkt === "abschluss_freigabe";
function zeichneRat() {
  const platz = document.getElementById("ratplatz");
  if (!platz) return;
  if (zustand.lauf && amRahmen(zustand.lauf)) { platz.replaceChildren(); zustand.ratSchluessel = null; return; }
  const rat = zustand.rat || {}, lauf = zustand.lauf;
  const sekunden = zustand.ratSeit ? Math.round((Date.now() - zustand.ratSeit) / 1000) : null;
  const denkt = (e) => !!(e && e.zustand === "laeuft");
  const schluessel = JSON.stringify([lauf && [lauf.thread_id, lauf.wartepunkt], platz.childElementCount,
                                     ["fable", "astra"].map((w) => rat[w] && [rat[w].zustand, rat[w].veraltet, rat[w].datei]),
                                     rat.vergleich, zustand.unterwegs, lauf && lauf.zustand.laeuft,
                                     denkt(rat.fable) || denkt(rat.astra) ? sekunden : 0]);
  if (schluessel === zustand.ratSchluessel) return;
  zustand.ratSchluessel = schluessel;
  const gesperrt = zustand.unterwegs || (lauf && lauf.zustand.laeuft);
  const knopfFuer = (wer, text) => el("button", { class: wer === "astra" ? "astra" : "fable",
    disabled: gesperrt || (wer === "beide" ? denkt(rat.fable) && denkt(rat.astra) : denkt(rat[wer])),
    text, onclick: () => frageRat(wer) });
  const knoepfe = el("div", { class: "knoepfe" },
    knopfFuer("fable", "🧠 Fable fragen"), knopfFuer("astra", "🛰️ Astra fragen"), knopfFuer("beide", "⚖️ Beide fragen"),
    rat.fable || rat.astra ? null
      : el("span", { class: "leise", text: "Fable (Claude) und Astra (Codex) lesen Spec, Tests und Plan und empfehlen (1–5 min)." }));
  const v = rat.vergleich;
  let leiste = null;
  if (v && rat.fable && rat.astra) {
    const f = rat.fable.rat.entscheidung, a = rat.astra.rat.entscheidung;
    leiste = v.einig
      ? el("div", { class: "meldung ok", text: `einig: beide empfehlen ${EMPFEHLUNG[f] || f}` })
      : el("div", { class: "meldung fehler", text: `uneinig: Fable ${EMPFEHLUNG[f] || f} · Astra ${EMPFEHLUNG[a] || a}. `
          + `Vorbelegt ist die vorsichtigere Empfehlung (${BERATER[v.vorbelegt].name}).` });
  }
  const karten = ["fable", "astra"].filter((w) => rat[w]).map((w) =>
    ratKarte(w, rat[w], v ? w === v.vorbelegt : true, gesperrt, sekunden));
  fuelle(platz, knoepfe, leiste, karten.length ? el("div", { class: "raete" }, karten) : null);
  const vorbelegt = v ? rat[v.vorbelegt] : [rat.astra, rat.fable].find((e) => e && e.zustand === "fertig" && !e.fehler);
  if (vorbelegt && vorbelegt.zustand === "fertig") vorfuellen(vorbelegt);
}
// ---------------------------------------------------------------------------------------------- Einwände (6b-1)
// Gegenstimme der anderen Modellfamilie oder uneinige Berater: freigeben/annehmen nur mit Begründung (landet im Bericht).
const DURCHLASS = ["freigeben", "annehmen", "mergen"];
function zeichneEinwand() {
  const platz = document.getElementById("einwandplatz");
  if (!platz) return;
  const einwaende = (zustand.lauf && zustand.lauf.einwaende) || [];
  const schluessel = JSON.stringify([zustand.lauf && zustand.lauf.checkpoint_id, einwaende]);
  if (schluessel === zustand.einwandSchluessel) return;
  zustand.einwandSchluessel = schluessel;
  const alt = document.getElementById("begruendung");
  const text = alt ? alt.value : "";  // Getipptes überlebt neue Einwände
  if (!einwaende.length) { fuelle(platz); return; }
  const feld = el("textarea", { id: "begruendung" });
  feld.value = text;
  fuelle(platz, el("div", { class: "karte einwand" },
    el("h3", { text: "⚠ Einwand: Freigeben nur mit Begründung" }),
    el("ul", { class: "punkte" }, einwaende.map((e) => el("li", { text: e }))),
    el("label", { for: "begruendung", text: "Warum trotzdem freigeben/annehmen/mergen? (landet im Bericht)" }), feld));
}
function begruendungFuer(body) {
  // null: Begründung fehlt; sonst body mit Begründung (oder unverändert, wenn keine nötig ist)
  const einwaende = (zustand.lauf && zustand.lauf.einwaende) || [];
  if (!DURCHLASS.includes(body.entscheidung) || !einwaende.length) return body;
  const feld = document.getElementById("begruendung");
  const text = feld ? feld.value.trim() : "";
  return text ? { ...body, begruendung: text } : null;
}
