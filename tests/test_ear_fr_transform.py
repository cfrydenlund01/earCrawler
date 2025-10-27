from earCrawler.transforms.ear_fr_to_rdf import extract_parts_from_text


def test_extract_parts():
    text = "Updates to 15 CFR Part 744 and 15 CFR Part 736."
    assert extract_parts_from_text(text) == {"744", "736"}
