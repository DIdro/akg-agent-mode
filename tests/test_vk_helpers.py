from channels.vk import _is_noise, _period_matches


def test_is_noise_protects_stats_dashboard():
    url = "https://web.api.vk.ru/method/statsDashboard.getOwnerStats?act=a1&gid=85520068"
    assert _is_noise(url) is False


def test_is_noise_protects_batch_call():
    url = "https://web.api.vk.ru/method/batch.call?act=a1&calls=%5B%5D"
    assert _is_noise(url) is False


def test_is_noise_blocks_stickers():
    url = "https://web.api.vk.ru/method/stickers.getSettings?act=a1&fields=all"
    assert _is_noise(url) is True


def test_is_noise_blocks_messenger_long_poll():
    url = "https://web.api.vk.ru/queuev4/wait?act=a_check&key=abc&ts=123"
    assert _is_noise(url) is True


def test_period_matches_equal_range():
    # Дашборд ВК иногда отдаёт обычный дефис вместо en-dash — должно
    # нормализоваться и совпасть с запрошенной неделей.
    assert _period_matches("13.07–19.07", "13.07-19.07") is True


def test_period_matches_different_range():
    assert _period_matches("13.07–19.07", "17.07–23.07") is False


def test_period_matches_empty_actual():
    assert _period_matches("13.07–19.07", "") is False
