import config


def test_webhook_defaults_none():
    assert config.WEBHOOK_URL is None
    assert config.WEBHOOK_KEY is None


def test_channels_have_registry_names():
    # dzen — одна строка реестра; vk — несколько (по вкладкам)
    assert isinstance(config.CHANNELS["dzen"]["registry"], str)
    vk_reg = config.CHANNELS["vk"]["registry"]
    assert isinstance(vk_reg, dict)
    assert "community" in vk_reg and "channel" in vk_reg and "video" in vk_reg
    assert isinstance(config.CHANNELS["tenchat"]["registry"], str)
