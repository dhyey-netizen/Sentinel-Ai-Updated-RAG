from pathlib import Path

from sentinel_ai.knowledge import RunbookIndex, chunk_markdown, tokenize

RUNBOOKS = Path(__file__).resolve().parent.parent / "data" / "runbooks"


def write(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")


def test_tokenize_drops_stopwords_and_stems_lightly():
    # The stemmer is deliberately conservative: plurals are folded, short words are left alone.
    assert tokenize("The pools were timed out") == ["pool", "timed", "out"]
    assert tokenize("connections") == ["connection"]
    assert "the" not in tokenize("the pool") and "pool" in tokenize("pools")


def test_chunking_by_heading_keeps_all_text():
    md = "# Title\nintro ignored\n\n## A\nalpha body\n\n## B\nbeta body\n"
    chunks = chunk_markdown("file", md)
    assert chunks == [("Title / A", "alpha body"), ("Title / B", "beta body")]


def test_long_sections_are_split_without_losing_text():
    para = "word " * 150  # 750 chars
    md = f"# T\n## S\n{para}\n\n{para}\n\n{para}\n"
    chunks = chunk_markdown("f", md)
    assert len(chunks) >= 2 and all(len(t) <= 900 for _, t in chunks)
    assert sum(t.count("word") for _, t in chunks) == 450


def test_missing_or_empty_directory_gives_empty_index(tmp_path):
    assert len(RunbookIndex.from_dir(tmp_path / "nope")) == 0
    assert len(RunbookIndex.from_dir(tmp_path)) == 0
    assert RunbookIndex.from_dir(tmp_path / "nope").search("anything") == []


def test_ids_are_stable_and_sources_are_file_stems(tmp_path):
    write(tmp_path, "b.md", "# B\n## S\nbeta text here")
    write(tmp_path, "a.md", "# A\n## S\nalpha text here")
    idx = RunbookIndex.from_dir(tmp_path)
    assert [(c.id, c.source) for c in idx.chunks] == [("K1", "a"), ("K2", "b")]


def test_bundled_runbooks_load():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    assert len(idx) >= 10
    assert {c.source for c in idx.chunks} >= {"pool-exhaustion", "db-timeouts", "upstream-timeouts"}


def test_retrieves_the_matching_runbook_first():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    top = idx.search("Connection is not available, request timed out waiting pool active idle")
    assert top and top[0].chunk.source == "pool-exhaustion"
    top = idx.search("upstream payment-gateway timed out circuit breaker retry")
    assert top[0].chunk.source == "upstream-timeouts"
    top = idx.search("NullPointerException after deployment release error rate")
    assert top[0].chunk.source == "deploy-regression"


def test_unrelated_or_vague_queries_return_nothing():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    assert idx.search("zzzz qqqq xxxx") == []
    assert idx.search("") == []
    assert idx.search("the a an of") == []  # only stopwords
    assert idx.search("checkout failed: internal error") == []  # vague: below the score floor


def test_single_runbook_cannot_fill_every_slot(tmp_path):
    body = "# R\n" + "".join(f"## S{i}\ncache redis connection reset failure\n" for i in range(5))
    write(tmp_path, "only.md", body)
    idx = RunbookIndex.from_dir(tmp_path)
    assert len(idx.search("redis connection reset", k=5, min_score=0.1)) == 2  # max_per_source


def test_search_is_deterministic():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    q = "database sql timeout slow query full table scan"
    assert [r.chunk.id for r in idx.search(q)] == [r.chunk.id for r in idx.search(q)]


def test_search_runbooks_returns_whole_best_runbook_in_order():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    got = idx.search_runbooks("Connection is not available request timed out pool waiting")
    assert {r.chunk.source for r in got} == {"pool-exhaustion"}
    headings = [r.chunk.heading.split(" / ")[-1] for r in got]
    assert headings == ["Symptoms", "Diagnosis", "Remediation"]  # sibling sections included
    assert len({r.score for r in got}) == 1  # each carries the runbook's best score


def test_search_runbooks_respects_max_and_floor():
    idx = RunbookIndex.from_dir(RUNBOOKS)
    q = "NullPointerException deployment error rate upstream timed out circuit breaker retry"
    assert len({r.chunk.source for r in idx.search_runbooks(q, max_runbooks=1)}) == 1
    assert idx.search_runbooks("zzzz qqqq") == []
