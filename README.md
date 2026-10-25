# MASTER ISO SUITE

Sistemi di gestione per PMI manifatturiere in un'unica applicazione Flask:

- **ISO 9001** — obiettivi, rischi e opportunità (§6), formazione, qualifiche e polivalenza (§7.2), manutenzione (§7.1.3), tarature (§7.1.5), archivio documentale controllato (§7.5), non conformità con metodo 8D (§8.7, §10.2), audit interni con rapporto per punti norma (§9.2), riesame della direzione con verbale Word (§9.3).
- **ISO 56001 / 56002** — strategia e politica dell'innovazione, raccolta e valutazione delle idee, portafoglio progetti a fasi e gate, indicatori, autovalutazione di maturità per capitolo.
- **ISO 14001** — aspetti e impatti ambientali, obblighi di conformità con scadenze, emergenze, autovalutazione per punto.
- **ISO 45001** — pericoli e valutazione dei rischi (P × G), requisiti legali D.Lgs. 81/08, infortuni e quasi infortuni, autovalutazione.
- **SA8000** — rischi sociali in azienda e nella catena di fornitura, requisiti 1-9, segnalazioni e reclami, autovalutazione.
- **VSME** — registro degli indicatori di sostenibilità e relazione da allegare al bilancio.

Ogni modulo è collegato nel cruscotto al punto della norma che soddisfa.

## Dati dimostrativi

Al primo avvio carica un'azienda simulata, **ACME Saldature Srl** (carpenteria e saldatura conto terzi). Persone, clienti, fornitori e numeri sono inventati. PIN demo: direzione `9999`, qualità `1111`, reparto `1234`.
Per l'uso reale: `DEMO_DATA=0`, `RAGIONE_SOCIALE`, `SEDE_LEGALE`.

## Avvio

```bash
pip install -r requirements.txt
flask --app wsgi run
python -m pytest -q
```

Su Railway: servizio PostgreSQL (`DATABASE_URL`), `SECRET_KEY`, un Volume montato in `/data` con `UPLOAD_FOLDER=/data/documenti`. Le bozze con AI del riesame e della relazione VSME usano `ANTHROPIC_API_KEY`, se presente.

© Maurizio Gustinicchi Consulting
