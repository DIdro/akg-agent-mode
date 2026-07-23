from channels.tenchat import map_stats_json


def test_map_stats_json_real_shape():
    # Форма, реально полученная от account/stats (живой прогон 2026-07-23).
    data = {"postViewCount": 12, "accountViewCount": 34, "subscribeCount": 5}
    assert map_stats_json(data) == {"reach": 12, "views": 34, "subscribers": 5}


def test_map_stats_json_plain_keys():
    data = {"reach": 0, "views": 0, "subscribers": 1}
    assert map_stats_json(data) == {"reach": 0, "views": 0, "subscribers": 1}


def test_map_stats_json_camel_case_variants():
    data = {"recordsReach": 12, "viewsCount": 34, "subscribersCount": 5}
    assert map_stats_json(data) == {"reach": 12, "views": 34, "subscribers": 5}


def test_map_stats_json_followers_synonym():
    data = {"reach": 0, "views": 0, "followers": 1}
    assert map_stats_json(data) == {"reach": 0, "views": 0, "subscribers": 1}


def test_map_stats_json_missing_keys_are_none():
    assert map_stats_json({}) == {"reach": None, "views": None, "subscribers": None}


def test_map_stats_json_zero_is_not_missing():
    # 0 — валидное значение (пустой профиль без записей), не должно
    # трактоваться как "ключ отсутствует".
    data = {"reach": 0, "views": 0, "subscribers": 0}
    assert map_stats_json(data) == {"reach": 0, "views": 0, "subscribers": 0}
