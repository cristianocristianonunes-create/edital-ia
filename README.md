# Edital IA

Reads Brazilian public procurement documents (editais) and turns them into a structured analysis with an LLM, with every claim pointing to the page it came from.

This is a Python port of the tender-analysis module of **Licitações IA**, a SaaS I built and run in production (Node.js). I rewrote it in Python with FastAPI, strict typing and tests, and checked it against the production data.

## What it does

1. **Extraction**: takes the files attached to a tender (PDF, DOCX, TXT and ZIP files containing them), detects the format from the file header (names from the government portal often have no extension) and extracts text page by page.
2. **Document selection**: when a tender is amended, the portal keeps every version ("Edital", "Edital_Retificado", "Edital_Segunda Retificação"). Only the newest one of each family is read. The main documents come first and newspaper notices come last, all within a character budget.
3. **Page map**: every page is tagged `[Arq N p. X]` and its position in the text is recorded, so the model can cite it and the citation can be checked.
4. **Analysis sheet**: Claude returns a JSON sheet covering deadlines, required documents, penalties, risks and items. The sheet is validated with Pydantic, and every `Arq N p. X` reference is checked against the pages that were actually read.
5. **Citation check**: for each quote the model gives as evidence, the code checks whether it exists on the cited page, on another page, or nowhere.

## API

| Method | Path | |
|---|---|---|
| GET | `/saude` | health check |
| POST | `/extrair` | multipart upload of the attachments → text, page map, per-file notes |
| POST | `/conferir` | model answer + text + page map → answer body and checked quotes |
| POST | `/ficha` | text + page map → validated analysis sheet, cost in USD, reference check |

The model sits behind a small `Protocol` (`ModeloIA`). Tests use a fake, so they never call the API or spend tokens. The real implementation streams the response, puts the tender in prompt cache (the prompt prefix is kept identical across calls) and records the cost.

## Running

```bash
docker build -t edital-py .
docker run --rm edital-py sh -c "pytest -q && mypy && ruff check ."   # 43 tests, mypy --strict, ruff
docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=... edital-py      # API at :8000/docs
```

## Checked against production

`scripts/paridade.py` reads the production database in read-only mode and compares this version with the Node one:

- Citation check: same results as Node on every stored answer.
- Analysis sheets: 90 page references in production, 100% pointing to a page that exists.

The production data is still small (an early-stage SaaS), so this is a sanity check rather than a statistical one.

## What I fixed or changed compared with the Node version

- **Page offsets were shifted by 2 characters.** The Node code trimmed the text after it had computed the page positions. I confirmed it on production data: all 228 pages of 3 tenders were off by exactly 2. The Python version recomputes the offsets after trimming, and a test covers it.
- **ZIP handling is safe.** Paths that try to leave the extraction folder (zip slip) are ignored, and the number of files and the uncompressed size are capped.
- **The sheet is validated, not just parsed.** A malformed or truncated answer is reported as such instead of being saved silently.
- **References are measured.** The share of references pointing to real pages is a simple quality metric, and it can be tracked across model or prompt changes.

## Next steps

- An evaluation set: a few tenders with a hand-checked sheet, scored on every prompt or model change.
- OCR for scanned PDFs (today they are reported as "no text").
- A job queue for long tenders instead of in-process background work.

---

Stack: Python 3.13, FastAPI, Pydantic v2, Anthropic SDK, pytest, mypy (strict), ruff, Docker, poppler.
Author: Cristiano Nunes ([portfolio](https://cnsinteligencia.com.br/cristiano/en)).
