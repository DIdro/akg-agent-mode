from channels.vk import _period_matches


def test_period_matches_equal_range():
    # Дашборд ВК иногда отдаёт обычный дефис вместо en-dash — должно
    # нормализоваться и совпасть с запрошенной неделей.
    assert _period_matches("13.07–19.07", "13.07-19.07") is True


def test_period_matches_different_range():
    assert _period_matches("13.07–19.07", "17.07–23.07") is False


def test_period_matches_empty_actual():
    assert _period_matches("13.07–19.07", "") is False
