# V1 Implementierungsvertrag

Python 3.11+, Paket `src/medizinanders`, CLI `ma`. Produktionsartefakte sind JSON,
Konfiguration und Vorlagen YAML (PyYAML); JSON Schema Draft 2020-12 (jsonschema).
Standardbibliothek unittest für Tests. Keine OpenAI-API, kein Server.

Artefakt common: artefakt_id A01..A12, projekt_id MA-YYYYMMDD-NNN, version SemVer,
datum ISO8601, autor nichtleer, status exakt Entwurf/geprüft/freigegeben/produziert/veröffentlicht,
eingaben [{artefakt_id,version,sha256}], quellen [source ids], offene_punkte [str],
gesperrt bool, sperrgrund str|null, beispiel bool (DEMO), inhalt object.
Immutable Speicherung artifacts/Axx/vVERSION.json; state.json.current[Axx] enthält
{version,path,sha256}. Der Orchestrator besitzt allein State/Freigaben, Worker nur result.json.

Abhängigkeiten: A01 []; A02 [A01]; A03 [A01,A02]; A04 [A03]; A05 [A03,A04];
A06 [A03,A04,A05]; A07 [A01,A02,A03,A04,A05,A06]; A08 [A07];
A09 [A05,A06,A08]; A10 [A07,A08,A09]; A11 [A05,A10]; A12 [A11].

Feldverträge inhalt:
- A01: kernfrage,nutzen,scope[],ausschluesse[],suchfragen[],format,ressourcen{},offene_entscheidungen[].
- A02: sources[] mit id,url,titel,typ,zugriff (geprueft|nicht_geprueft),fundstelle,
  abgerufen_am,sha256 nullable,original_geoeffnet bool,lokaler_pfad nullable,
  klinische_parameter {population,design,vergleich,endpunkt,absolute_wirkung,relative_wirkung,
  unsicherheit,interessenkonflikte,grenzen} alle str|null; suchprotokoll[],gegenbelege[],
  korrekturen_retraktionen[]. Suchtreffer != verifiziert.
- A03: claims[] {id,text,status (BESTÄTIGT|TEILWEISE|WIDERLEGT|UNBEWIESEN),
  einsatz (ja|nur_mit_einschraenkung|nein),source_ids[],fundstellen[],gegenbelege[],
  einschraenkungen[],risiken[],medizinisch_relevant bool,rechtlich_relevant bool,
  art (sachverhalt|quellenbehauptung)}; faktenmatrix[],risikoübersicht[],psychologie_map[],
  medical_review_required bool,legal_review_required bool.
- A04: profil MA-SHORT-58-v1.0,abschnitte[] {funktion,start_ms,ende_ms},
  dramaturgie,cta_anzahl 1.
- A05: sprechertext,wortzahl,saetze[] {id,text,faktisch bool,claim_ids[],funktion},
  untertitel_basis,aussprache[],overlays[],titel,thumbnail,beschreibung (jeweils statement:
  {text,faktisch,claim_ids}),quellenangaben[],cta {text,faktisch,claim_ids},disclaimer string.
  Overlays gleiche statement-Form plus start_ms,ende_ms. Keine Inline-Ausnahmen für Fakten.
- A06: szenen[] {id,start_ms,ende_ms,sprechertext,funktion,motiv,assets[],sync_anker,
  overlay,quellenhinweis,uebergang,audio {voiceover bool,musik bool},claim_ids[]};
  assets[] {id,typ,herkunft,recht_status (geklaert|offen),nachweis,ki_illustration bool,
  imitierte_stimme bool}; invideo_prompt string.
- A07: ergebnis (freigabefaehig|nacharbeit_erforderlich|pruefung_unvollstaendig),
  findings[] {id,datei,problem,soll,ist,schwere K0|K1|K2,rueckweg,offen bool},
  pflichtpruefungen[] {id,anwendbar bool,erledigt bool,nachweis},freeze string|null.
- A08: preview {path,sha256},render_real bool,operator string,render_zeitpunkt,freeze.
- A09: final {path,sha256},srt {path,sha256},aenderungen[],musik_entfernt bool,
  getrennte_spuren bool,ducking_db number|null.
- A10: technische_reports[],findings[] wie A07,pflichtpruefungen[] wie A07,
  ergebnis wie A07,preview_sha256,final_sha256 nullable.
- A11: final_sha256,youtube_id nullable,url nullable,visibility (vorbereitet|privat|oeffentlich),
  ki_kennzeichnung bool|null,zielgruppe str|null,werbung bool|null,
  playback_pruefung object|null,veroeffentlicht_am str|null.
- A12: datenquelle,zeitraum,metriken object (jede {wert:number|null,begruendung:str|null}),
  beobachtungen[],hypothesen[],naechster_test (genau 1 string),regel_aenderung false.

Validation API `validate_artifact(data, artifacts=None, production=False) -> list[str]`,
`validate_bundle(artifacts, production=False) -> list[str]`; keine Mutation.
Media API `inspect_video(path, report_dir) -> dict` mit ergebnis, checks[],
sha256; Check {id,status bestanden|fehlgeschlagen|nicht_geprueft,ist,soll,grund}.
Subtitle API `validate_srt(path, font_path=None) -> dict` gleiche Checks,
`generate_srt(A05_inhalt,A06_inhalt)->str`. Unmessbare Werte nie erfinden.

Core stellt errors.PipelineError bereit. Alle unabhängigen Worker erhalten nur
aufgelistete Inputs und Role-Prompt. BETA Output ist {artifacts:[A04,A05,A06]},
andere Worker {artifacts:[Ax]}. result.json allein ist importierbar. Demo separat.

Tests dürfen Human-Callback in Python injizieren; Produktiv-CLI fordert interaktiv
konkrete Bestätigung, keine --yes Option. DEMO-Freigaben stets typ DEMO_SIMULATION.
