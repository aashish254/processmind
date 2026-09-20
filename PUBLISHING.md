# Publishing ProcessMind as an Independent Author — Step-by-Step

Everything here is **free**. The repo is already prepared: it's a clean git repository with a `LICENSE` (MIT), `CITATION.cff`, `.zenodo.json`, and a passing test suite. You just need to create the accounts and click a few buttons.

> **You only need to do the steps marked [YOU].** Everything else is already done.

---

## STEP 1 — Get an ORCID iD (your permanent author identity)  [YOU · ~5 min]

An ORCID iD is a free, permanent identifier that makes "Aashish" unambiguous as an author across arXiv, Zenodo, and journals.

1. Go to https://orcid.org → **Register**.
2. Fill in your name and email. You'll get an ID like `0000-0002-XXXX-XXXX`.
3. **Add it to your files** (optional but recommended): open `CITATION.cff` and put it on the `orcid:` line.

---

## STEP 2 — Push the code to GitHub  [YOU · ~10 min]

The repo is already committed locally. To publish it:

```bash
# 1. Create a free GitHub account at https://github.com (if you don't have one)

# 2. Create a new EMPTY repository:
#    GitHub → top-right "+" → "New repository"
#    Name: processmind   ·   Public   ·   DON'T check "Add README/.gitignore/License"
#    (they already exist here)

# 3. From this folder, connect and push (replace aashish254):
cd "/Users/aashish/Migrated_Caps/MASTERS CAP1"
git remote add origin https://github.com/aashish254/processmind.git
git branch -M main
git push -u origin main
```

4. Edit `CITATION.cff` and replace `aashish254` in `repository-code` with your real username, then `git add CITATION.cff && git commit -m "Set repository URL" && git push`.

**Why:** GitHub hosts the code publicly for free; it also auto-shows the "Cite this repository" button (powered by `CITATION.cff`).

---

## STEP 3 — Archive it on Zenodo → get a permanent DOI  [YOU · ~10 min]

Zenodo (run by CERN, free) gives your software a **DOI** — a permanent, citable link that never breaks, even if you delete the GitHub repo.

1. Go to https://zenodo.org → **Log in with GitHub**.
2. Click your name (top right) → **GitHub**.
3. Flip the toggle **ON** next to your `processmind` repo.
4. Back on GitHub: go to your repo → **Releases** → **Draft a new release**:
   - Tag: `v1.0.0`  →  Target: `main`  →  Title: `ProcessMind v1.0.0`  →  **Publish release**.
5. Zenodo detects the release within a minute and mints a DOI. Copy it.
6. Add the DOI badge to `README.md` (Zenodo gives you the markdown snippet) and push.

**Result:** your software is now permanently citable as `Aashish. (2026). ProcessMind (v1.0.0) [Software]. Zenodo. https://doi.org/...`

---

## STEP 4 — Publish the thesis as a preprint  [YOU · ~15 min]

`thesis/thesis.pdf` is ready. Two free homes — do **both**:

**(a) Zenodo (easiest — no endorsement needed):**
1. https://zenodo.org → **New upload**.
2. Upload `thesis/thesis.pdf`.
3. Resource type: **Publication → Working paper / Preprint**. Title, your name (linked to your ORCID), abstract = the thesis abstract. License: CC-BY-4.0.
4. Publish → you get a **second DOI** for the paper itself.

**(b) arXiv (more visibility in CS):**
1. Register at https://arxiv.org (free).
2. Submit the PDF. Category: **cs.SE** (Software Engineering) or **cs.AI**.
3. ⚠️ First-time independent submitters may be asked for an **endorsement**. If prompted, you can request endorsement through arXiv's system — or simply rely on Zenodo (Step 4a), which has no such gate.

---

## STEP 5 — (Optional, best credibility) Turn it into a short workshop paper

The thesis is ~18k words; venues want 10–15 pages. The strongest sellable core is:
- the **unified E1–E6 benchmark** (first commensurable comparison of rule / LLM / mining extractors),
- the **soundness-by-construction result** (E6 fitness = coverage on all 7 logs), and
- the **fallback-transparency finding** (recorded-method logging caught a silent fallback — a genuinely novel, defensible methodological point).

Good-fit, low/free-cost venues: **BPM Demo track**, **CAiSE workshops**, **ICPM workshops**, **EMISAJ** (free journal, no APC). I can restructure the thesis into a paper skeleton whenever you're ready.

---

## What I already did for you ✅
- `LICENSE` (MIT, your name)
- `CITATION.cff` — powers GitHub's "Cite this repository"
- `.zenodo.json` — powers Zenodo's auto-archive metadata
- Clean git repo, one commit, no secrets, no bulky regenerable outputs
- `pyproject.toml` author set to you
- All 6 real figures + corrected citations in `thesis.docx` / `thesis.pdf`

## 2-month timeline
| When | Milestone |
|---|---|
| **Week 1** | Steps 1–4 done → code + thesis are public and citable |
| **Weeks 2–4** | (Optional) I help you write the 10–12 page workshop paper |
| **Weeks 4–8** | Submit to a workshop; keep the Zenodo/arXiv preprint as the live citable record |
