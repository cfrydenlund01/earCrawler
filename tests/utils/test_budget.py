from earCrawler.utils import budget


def test_budget_consume_and_reset():
    budget.reset("test")
    with budget.consume("test", limit=2):
        pass
    with budget.consume("test", limit=2):
        pass
    try:
        with budget.consume("test", limit=2):
            pass
    except budget.BudgetExceededError:
        pass
    else:
        assert False, "expected budget failure"
    budget.reset("test")
    with budget.consume("test", limit=1):
        pass
