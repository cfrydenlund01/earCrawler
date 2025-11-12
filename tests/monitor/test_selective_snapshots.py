from earCrawler.kg.delta import select_impacted_queries


def test_impacted_queries_selection():
    tag_map = {"a.rq": ["entity", "other"], "b.rq": ["other"]}
    changed = ["entity"]
    impacted = select_impacted_queries(changed, tag_map)
    assert impacted == ["a.rq"]
